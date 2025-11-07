/* $Id: VBoxServiceVMInfo.cpp 111576 2025-11-07 18:42:24Z knut.osmundsen@oracle.com $ */
/** @file
 * VBoxService - Virtual Machine Information for the Host.
 */

/*
 * Copyright (C) 2009-2025 Oracle and/or its affiliates.
 *
 * This file is part of VirtualBox base platform packages, as
 * available from https://www.virtualbox.org.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation, in version 3 of the
 * License.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, see <https://www.gnu.org/licenses>.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

/** @page pg_vgsvc_vminfo VBoxService - VM Information
 *
 * The VM Information subservice provides heaps of useful information about the
 * VM via guest properties.
 *
 * Guest properties is a limited database maintained by the HGCM GuestProperties
 * service in cooperation with the Main API (VBoxSVC).  Properties have a name
 * (ours are path-like), a string value, and a nanosecond timestamp (unix epoch
 * base).  The timestamp lets the user see how recent the information is.  As an
 * laternative to polling on changes, it is also possible to wait on changes via
 * the Main API or VBoxManage on the host side and VBoxControl in the guest.
 *
 * The namespace "/VirtualBox/" is reserved for value provided by VirtualBox.
 *
 * This subservice provides all the information under "/VirtualBox/GuestInfo/" (
 * except for (some stupid reson) "/VirtualBox/GuestInfo/OS/AutoLogonStatus"
 * which is written by the GINA and credential provider plugins on Windows) and
 * some bits under "/VirtualBox/GuestAdd/"
 *
 * The properties are either of a fixed or transient (changing/temporary) in
 * nature. The fixed properties are typically updated only when the subservice
 * starts and the transient ones are updated at an interval.
 *
 *
 * @section sec_vgsvc_vminfo_fixed      Fixed Properties
 *
 * To the fixed properties belong things like guest OS version, additions
 * version, additions installation path and component info.
 *
 *
 * @section sec_vgsvc_vminfo_transient  Transient Properties & Caching
 *
 * Transient properties provided by this subservice are for things are may
 * change over time, for instance network addresses, the number of logged in
 * users and such.  These properties will be delete (or in rare cases set to a
 * special value) when the subservice is shut down.  When the VM is reset or
 * powered off they will deleted.
 *
 * They are updated by the subservice every so often, with the interval given by
 * the --vminfo-interval or --interval options.
 *
 * While the information provided by these properties is volatile, it is
 * typically not changing at every update interval.  So, to avoid frequent
 * writing of the same info to the host, we use a 'cache' to track the
 * information we've already written to the host and how to deal with it when
 * the subservice shuts down.  (While the 'cache' can be used for fixed
 * properties, it is currently only used for transient ones and therefore it
 * defaults to the standard transient behaviour when adding new entries to it.)
 *
 *
 * @section sec_vgsvc_vminfo_beacons    Beacons
 *
 * As mentioned, the subservice does not write properties unless there are
 * changes. So, in order for the host side to know that information is up to
 * date despite an oldish timestamp we define a couple of values that are always
 * updated and can reliably used to figure how old the information actually is.
 *
 * For the networking part "/VirtualBox/GuestInfo/Net/Count" is the value to
 * watch out for.
 *
 * For the login part "/VirtualBox/GuestInfo/OS/LoggedInUsers" is the value to
 * watch, starting with VBox 7.2.6.
 *
 *
 * @section sec_vgsvc_vminfo_properties Property List
 *
 * @todo list the properties with some explanation.
 *
 *
 */


/*********************************************************************************************************************************
*   Header Files                                                                                                                 *
*********************************************************************************************************************************/
#ifdef RT_OS_WINDOWS
# include <iprt/win/winsock2.h>
# include <iprt/win/iphlpapi.h>
# include <iprt/win/ws2tcpip.h>
# include <iprt/win/windows.h>
# include <Ntsecapi.h>
#else
# define __STDC_LIMIT_MACROS
# include <arpa/inet.h>
# include <errno.h>
# include <netinet/in.h>
# include <sys/ioctl.h>
# include <sys/socket.h>
# include <net/if.h>
# include <pwd.h> /* getpwuid */
# include <unistd.h>
# if !defined(RT_OS_OS2) && !defined(RT_OS_FREEBSD) && !defined(RT_OS_HAIKU)
#  include <utmpx.h> /** @todo FreeBSD 9 should have this. */
# endif
# ifdef RT_OS_OS2
#  include <net/if_dl.h>
# endif
# ifdef RT_OS_SOLARIS
#  include <sys/sockio.h>
#  include <net/if_arp.h>
# endif
# if defined(RT_OS_DARWIN) || defined(RT_OS_FREEBSD) || defined(RT_OS_NETBSD)
#  include <ifaddrs.h> /* getifaddrs, freeifaddrs */
#  include <net/if_dl.h> /* LLADDR */
#  include <netdb.h> /* getnameinfo */
# endif
# ifdef VBOX_WITH_DBUS
#  include <VBox/dbus.h>
# endif
#endif

#include <iprt/mem.h>
#include <iprt/thread.h>
#include <iprt/string.h>
#include <iprt/semaphore.h>
#include <iprt/system.h>
#include <iprt/time.h>
#include <iprt/assert.h>
#include <VBox/err.h>
#include <VBox/version.h>
#include <VBox/VBoxGuestLib.h>
#include <VBox/HostServices/GuestPropertySvc.h> /* For GUEST_PROP_MAX_VALUE_LEN and GUEST_PROP_MAX_NAME_LEN.  */
#include "VBoxServiceInternal.h"
#include "VBoxServiceUtils.h"
#include "VBoxServicePropCache.h"


/** Structure containing information about a location awarness
 *  client provided by the host. */
/** @todo Move this (and functions) into VbglR3. */
typedef struct VBOXSERVICELACLIENTINFO
{
    uint32_t    uID;
    char       *pszName;
    char       *pszLocation;
    char       *pszDomain;
    bool        fAttached;
    uint64_t    uAttachedTS;
} VBOXSERVICELACLIENTINFO, *PVBOXSERVICELACLIENTINFO;


/*********************************************************************************************************************************
*   Global Variables                                                                                                             *
*********************************************************************************************************************************/
/** The vminfo interval (milliseconds). */
static uint32_t                 g_cMsVMInfoInterval = 0;
/** The semaphore we're blocking on. */
static RTSEMEVENTMULTI          g_hVMInfoEvent = NIL_RTSEMEVENTMULTI;
/** The guest property service client session details. */
static VBGLGSTPROPCLIENT        g_VMInfoGuestPropSvcClient;
/** Number of currently logged in users in OS. */
static uint32_t                 g_cVMInfoLoggedInUsers = 0;
/** The guest property cache. */
static VBOXSERVICEVEPROPCACHE   g_VMInfoPropCache;
static const char              *g_pszPropCacheValLoggedInUsersList = "/VirtualBox/GuestInfo/OS/LoggedInUsersList";
static const char              *g_pszPropCacheValLoggedInUsers     = "/VirtualBox/GuestInfo/OS/LoggedInUsers";
static const char              *g_pszPropCacheValNoLoggedInUsers   = "/VirtualBox/GuestInfo/OS/NoLoggedInUsers";
static const char              *g_pszPropCacheValNetCount          = "/VirtualBox/GuestInfo/Net/Count";
#ifdef RT_OS_WINDOWS
/** A guest user's guest property root key. */
static const char              *g_pszPropCacheKeyUser              = "/VirtualBox/GuestInfo/User";
#endif
/** The VM session ID. Changes whenever the VM is restored or reset. */
static uint64_t                 g_idVMInfoSession;
/** The last attached locartion awareness (LA) client timestamp. */
static uint64_t                 g_LAClientAttachedTS = 0;
/** The current LA client info. */
static VBOXSERVICELACLIENTINFO  g_LAClientInfo;
/** User idle threshold (in ms). This specifies the minimum time a user is considered
 *  as being idle and then will be reported to the host. Default is 5s. */
uint32_t                        g_uVMInfoUserIdleThresholdMS = 5 * 1000;


/*********************************************************************************************************************************
*   Defines                                                                                                                      *
*********************************************************************************************************************************/
static const char *g_pszLAActiveClient = "/VirtualBox/HostInfo/VRDP/ActiveClient";

#ifdef VBOX_WITH_DBUS
/** @name ConsoleKit defines (taken from 0.4.5).
 * @{ */
# define CK_NAME                "org.freedesktop.ConsoleKit"            /* unused */
# define CK_PATH                "/org/freedesktop/ConsoleKit"           /* unused */
# define CK_INTERFACE           "org.freedesktop.ConsoleKit"
# define CK_MANAGER_PATH        "/org/freedesktop/ConsoleKit/Manager"
# define CK_MANAGER_INTERFACE   "org.freedesktop.ConsoleKit.Manager"
# define CK_SEAT_INTERFACE      "org.freedesktop.ConsoleKit.Seat"       /* unused */
# define CK_SESSION_INTERFACE   "org.freedesktop.ConsoleKit.Session"
/** @} */
/** @name systemd-logind defines
 * @{ */
# define SYSTEMD_LOGIN_INTERFACE           "org.freedesktop.login1"
# define SYSTEMD_LOGIN_PATH                "/org/freedesktop/login1"
# define SYSTEMD_LOGIN_MANAGER_INTERFACE   "org.freedesktop.login1.Manager"
# define SYSTEMD_LOGIN_SESSION_INTERFACE   "org.freedesktop.login1.Session"
/** @} */
#endif



/**
 * Signals the event so that a re-enumeration of VM-specific
 * information (like logged in users) can happen.
 *
 * @return  IPRT status code.
 */
int VGSvcVMInfoSignal(void)
{
    /* Trigger a re-enumeration of all logged-in users by unblocking
     * the multi event semaphore of the VMInfo thread. */
    if (g_hVMInfoEvent)
        return RTSemEventMultiSignal(g_hVMInfoEvent);

    return VINF_SUCCESS;
}


/**
 * @interface_method_impl{VBOXSERVICE,pfnPreInit}
 */
static DECLCALLBACK(int) vbsvcVMInfoPreInit(void)
{
    return VINF_SUCCESS;
}


/**
 * @interface_method_impl{VBOXSERVICE,pfnOption}
 */
static DECLCALLBACK(int) vbsvcVMInfoOption(const char **ppszShort, int argc, char **argv, int *pi)
{
    /** @todo Use RTGetOpt here. */

    int rc = -1;
    if (ppszShort)
        /* no short options */;
    else if (!strcmp(argv[*pi], "--vminfo-interval"))
        rc = VGSvcArgUInt32(argc, argv, "", pi, &g_cMsVMInfoInterval, 1, UINT32_MAX - 1);
    else if (!strcmp(argv[*pi], "--vminfo-user-idle-threshold"))
        rc = VGSvcArgUInt32(argc, argv, "", pi, &g_uVMInfoUserIdleThresholdMS, 1, UINT32_MAX - 1);
    return rc;
}


/**
 * @interface_method_impl{VBOXSERVICE,pfnInit}
 */
static DECLCALLBACK(int) vbsvcVMInfoInit(void)
{
    /*
     * If not specified, find the right interval default.
     * Then create the event sem to block on.
     */
    if (!g_cMsVMInfoInterval)
        g_cMsVMInfoInterval = g_cSecDefaultInterval * 1000;
    if (!g_cMsVMInfoInterval)
    {
        /* Set it to 5s by default for location awareness checks. */
        g_cMsVMInfoInterval = 5 * 1000;
    }

    int rc = RTSemEventMultiCreate(&g_hVMInfoEvent);
    AssertRCReturn(rc, rc);

    /* Get the session ID. The status code is ignored as this information is
       not available with VBox < 3.2.10. */
    VbglR3QuerySessionId(&g_idVMInfoSession);

    /* Initialize the LA client object. */
    RT_ZERO(g_LAClientInfo);

    rc = VbglGuestPropConnect(&g_VMInfoGuestPropSvcClient);
    if (RT_SUCCESS(rc))
    {
        VGSvcVerbose(3, "Property Service Client ID: %#x\n", g_VMInfoGuestPropSvcClient.idClient);

        rc = VGSvcPropCacheInit(&g_VMInfoPropCache, &g_VMInfoGuestPropSvcClient);
        if (RT_SUCCESS(rc))
        {
            /*
             * Declare the beacons.
             *
             * We ignore errors here, though, we probably shouldn't as the only
             * error is running out of memory or process corruption.
             */
            int rc2 = VGSvcPropCacheDeclareEntry(&g_VMInfoPropCache, g_pszPropCacheValLoggedInUsers,
                                                 VGSVCPROPCACHE_FLAGS_TMP_DEL_TRANSRESET | VGSVCPROPCACHE_FLAGS_ALWAYS_UPDATE);
            AssertLogRelRC(rc2);

            rc2 = VGSvcPropCacheDeclareEntry(&g_VMInfoPropCache, g_pszPropCacheValNetCount,
                                             VGSVCPROPCACHE_FLAGS_TMP_DEL_TRANSRESET | VGSVCPROPCACHE_FLAGS_ALWAYS_UPDATE);
            AssertLogRelRC(rc2);

            /*
             * Get configuration guest properties from the host.
             * Note: All properties should have sensible defaults in case the lookup here fails.
             */
            char *pszValue;
            rc2 = VGSvcReadHostProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestAdd/VBoxService/--vminfo-user-idle-threshold",
                                    true /* Read only */, &pszValue, NULL /* Flags */, NULL /* Timestamp */);
            if (RT_SUCCESS(rc2))
            {
                AssertPtr(pszValue);
                g_uVMInfoUserIdleThresholdMS = RTStrToUInt32(pszValue);
                g_uVMInfoUserIdleThresholdMS = RT_CLAMP(g_uVMInfoUserIdleThresholdMS, 1000, UINT32_MAX - 1);
                RTStrFree(pszValue);
            }

            return VINF_SUCCESS;
        }

        VGSvcError("Failed to init guest property cache: %Rrc\n", rc);
        VbglGuestPropDisconnect(&g_VMInfoGuestPropSvcClient);
    }
    /* If the service was not found, we disable this service without
       causing VBoxService to fail. */
    else if (rc == VERR_HGCM_SERVICE_NOT_FOUND) /* Host service is not available. */
    {
        VGSvcVerbose(0, "Guest property service is not available, disabling the service\n");
        rc = VERR_SERVICE_DISABLED;
    }
    else
        VGSvcError("Failed to connect to the guest property service! Error: %Rrc\n", rc);

    RTSemEventMultiDestroy(g_hVMInfoEvent);
    g_hVMInfoEvent = NIL_RTSEMEVENTMULTI;
    return rc;
}


/**
 * Retrieves a specifiy client LA property.
 *
 * @return  IPRT status code.
 * @param   idLAClient              LA client ID to retrieve property for.
 * @param   pszProperty             Property (without path) to retrieve.
 * @param   ppszValue               Where to store value of property.
 * @param   puTimestamp             Timestamp of property to retrieve. Optional.
 */
static int vgsvcGetLAClientValue(uint32_t idLAClient, const char *pszProperty, char **ppszValue, uint64_t *puTimestamp)
{
    AssertReturn(idLAClient, VERR_INVALID_PARAMETER);
    AssertPtrReturn(pszProperty, VERR_INVALID_POINTER);

    int  rc;
    char szFullPropNm[GUEST_PROP_MAX_NAME_LEN];
    if (RTStrPrintf2(szFullPropNm, sizeof(szFullPropNm),
                     "/VirtualBox/HostInfo/VRDP/Client/%RU32/%s", idLAClient, pszProperty) > 0)
        rc = VGSvcReadHostProp(&g_VMInfoGuestPropSvcClient, szFullPropNm, true /*fReadOnly*/,
                               ppszValue, NULL /*fFlags*/, puTimestamp);
    else
        rc = VERR_FILENAME_TOO_LONG;
    return rc;
}


/**
 * Retrieves LA client information. On success the returned structure will have allocated
 * objects which need to be free'd with vboxServiceFreeLAClientInfo.
 *
 * @return  IPRT status code.
 * @param   uClientID               Client ID to retrieve information for.
 * @param   pClient                 Pointer where to store the client information.
 */
static int vgsvcGetLAClientInfo(uint32_t uClientID, PVBOXSERVICELACLIENTINFO pClient)
{
    AssertReturn(uClientID, VERR_INVALID_PARAMETER);
    AssertPtrReturn(pClient, VERR_INVALID_POINTER);

    int rc = vgsvcGetLAClientValue(uClientID, "Name", &pClient->pszName,
                                         NULL /* Timestamp */);
    if (RT_SUCCESS(rc))
    {
        char *pszAttach;
        rc = vgsvcGetLAClientValue(uClientID, "Attach", &pszAttach, &pClient->uAttachedTS);
        if (RT_SUCCESS(rc))
        {
            AssertPtr(pszAttach);
            pClient->fAttached = RTStrICmp(pszAttach, "1") == 0;

            RTStrFree(pszAttach);
        }
    }
    if (RT_SUCCESS(rc))
        rc = vgsvcGetLAClientValue(uClientID, "Location", &pClient->pszLocation, NULL /* Timestamp */);
    if (RT_SUCCESS(rc))
        rc = vgsvcGetLAClientValue(uClientID, "Domain", &pClient->pszDomain, NULL /* Timestamp */);
    if (RT_SUCCESS(rc))
        pClient->uID = uClientID;

    return rc;
}


/**
 * Frees all allocated LA client information of a structure.
 *
 * @param   pClient                 Pointer to client information structure to free.
 */
static void vgsvcFreeLAClientInfo(PVBOXSERVICELACLIENTINFO pClient)
{
    if (pClient)
    {
        if (pClient->pszName)
        {
            RTStrFree(pClient->pszName);
            pClient->pszName = NULL;
        }
        if (pClient->pszLocation)
        {
            RTStrFree(pClient->pszLocation);
            pClient->pszLocation = NULL;
        }
        if (pClient->pszDomain)
        {
            RTStrFree(pClient->pszDomain);
            pClient->pszDomain = NULL;
        }
    }
}

#ifdef RT_OS_WINDOWS

/**
 * Updates a per-guest user guest property inside the given property cache.
 *
 * @return  VBox status code.
 * @retval  VERR_BUFFER_OVERFLOW if the final property name length exceeds the maximum supported length.
 * @param   pCache                  Pointer to guest property cache to update user in.
 * @param   pszUser                 Name of guest user to update.
 * @param   pszDomain               Domain of guest user to update. Optional.
 * @param   pszKey                  Key name of guest property to update.
 * @param   pszValue                Guest property value to set. Pass NULL for
 *                                  deleting the property.
 */
int VGSvcVMInfoUpdateUser(PVBOXSERVICEVEPROPCACHE pCache, const char *pszUser, const char *pszDomain,
                          const char *pszKey, const char *pszValue)
{
    AssertPtrReturn(pCache, VERR_INVALID_POINTER);
    Assert(pCache == &g_VMInfoPropCache);
    AssertPtrReturn(pszUser, VERR_INVALID_POINTER);
    AssertPtrNullReturn(pszDomain, VERR_INVALID_POINTER);
    AssertPtrReturn(pszKey, VERR_INVALID_POINTER);

    /*
     * We limit guest property names to 64 characters (see GUEST_PROP_MAX_NAME_LEN,
     * including terminator). So, we need to make sure the stuff we want to write
     * as a value fits into that space. See bugref{10575}.
     */
    char szName[GUEST_PROP_MAX_NAME_LEN];
    AssertCompile(GUEST_PROP_MAX_NAME_LEN == 64); /* Can we improve stuff once we (ever) raise this limit? */

    /* Try to write things the legacy way first.
       bird: Confused as to what 'legacy' refers to here, but it's possibly the pszDomain == NULL situation. */
    ssize_t const cchName = pszDomain
                          ? RTStrPrintf2(szName, sizeof(szName), "%s/%s@%s/%s", g_pszPropCacheKeyUser, pszUser, pszDomain, pszKey)
                          : RTStrPrintf2(szName, sizeof(szName), "%s/%s/%s",    g_pszPropCacheKeyUser, pszUser, pszKey);

    /* Did we exceed the length limit? Tell the caller to try again with some more sane values. */
    if (cchName < 0)
        return VERR_BUFFER_OVERFLOW;

    /*
     * Set the property.
     */
    return VGSvcPropCacheUpdate(pCache, szName, pszValue);
}


/**
 * Updates a per-guest user guest property inside the given property cache.
 *
 * @return  VBox status code.
 * @retval  VERR_BUFFER_OVERFLOW if the final property name length exceeds the maximum supported length.
 * @retval  VERR_INVALID_PARAMETER if the value is too long.
 * @param   pCache                  Pointer to guest property cache to update user in.
 * @param   pszUser                 Name of guest user to update.
 * @param   pszDomain               Domain of guest user to update. Optional.
 * @param   pszKey                  Key name of guest property to update.
 * @param   pszValueFormat          Guest property value (format string) to set.
 *                                  Pass NULL for deleting the property.
 * @param   va                      Format arguments.
 */
int VGSvcVMInfoUpdateUserV(PVBOXSERVICEVEPROPCACHE pCache, const char *pszUser, const char *pszDomain,
                           const char *pszKey, const char *pszValueFormat, va_list va)
{
    int rc;
    if (pszValueFormat)
    {
        AssertPtrReturn(pszValueFormat, VERR_INVALID_POINTER);

        char    szValue[GUEST_PROP_MAX_VALUE_LEN];
        ssize_t cchValue = RTStrPrintf2V(szValue, sizeof(szValue), pszValueFormat, va);
        if (cchValue >= 0)
            rc = VGSvcVMInfoUpdateUser(pCache, pszUser, pszDomain, pszKey, szValue);
        else
            rc = VERR_INVALID_PARAMETER;
    }
    else
        rc = VGSvcVMInfoUpdateUser(pCache, pszUser, pszDomain, pszKey, NULL);
    return rc;
}


/**
 * Updates a per-guest user guest property inside the given property cache.
 *
 * @return  VBox status code.
 * @retval  VERR_BUFFER_OVERFLOW if the final property name length exceeds the maximum supported length.
 * @retval  VERR_INVALID_PARAMETER if the value is too long.
 * @param   pCache                  Pointer to guest property cache to update user in.
 * @param   pszUser                 Name of guest user to update.
 * @param   pszDomain               Domain of guest user to update. Optional.
 * @param   pszKey                  Key name of guest property to update.
 * @param   pszValueFormat          Guest property value (format string) to set.
 *                                  Pass NULL for deleting the property.
 * @param   ...                     Format arguments.
 */
int VGSvcVMInfoUpdateUserF(PVBOXSERVICEVEPROPCACHE pCache, const char *pszUser, const char *pszDomain,
                           const char *pszKey, const char *pszValueFormat, ...)
{
    va_list va;
    va_start(va, pszValueFormat);
    int rc = VGSvcVMInfoUpdateUserV(pCache, pszUser, pszDomain, pszKey, pszValueFormat, va);
    va_end(va);
    return rc;
}

#endif /* RT_OS_WINDOWS */

/**
 * Writes the properties that won't change while the service is running.
 *
 * Errors are ignored.
 */
static void vgsvcVMInfoWriteFixedProperties(void)
{
    /*
     * First get OS information that won't change.
     */
    char szInfo[GUEST_PROP_MAX_VALUE_LEN];
    int rc = RTSystemQueryOSInfo(RTSYSOSINFO_PRODUCT, szInfo, sizeof(szInfo));
    if (RT_FAILURE(rc) && rc != VERR_BUFFER_OVERFLOW) szInfo[0] = '\0';
    VGSvcWriteProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestInfo/OS/Product", szInfo);

    rc = RTSystemQueryOSInfo(RTSYSOSINFO_RELEASE, szInfo, sizeof(szInfo));
    if (RT_FAILURE(rc) && rc != VERR_BUFFER_OVERFLOW) szInfo[0] = '\0';
    VGSvcWriteProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestInfo/OS/Release", szInfo);

    rc = RTSystemQueryOSInfo(RTSYSOSINFO_VERSION, szInfo, sizeof(szInfo));
    if (RT_FAILURE(rc) && rc != VERR_BUFFER_OVERFLOW) szInfo[0] = '\0';
    VGSvcWriteProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestInfo/OS/Version", szInfo);

    rc = RTSystemQueryOSInfo(RTSYSOSINFO_SERVICE_PACK, szInfo, sizeof(szInfo));
    if (RT_FAILURE(rc) && rc != VERR_BUFFER_OVERFLOW) szInfo[0] = '\0';
    VGSvcWriteProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestInfo/OS/ServicePack", szInfo);

    /*
     * Retrieve version information about Guest Additions and installed files (components).
     */
    char *pszAddVer;
    char *pszAddVerExt;
    char *pszAddRev;
    rc = VbglR3QueryAdditionsVersion(&pszAddVer, &pszAddVerExt, &pszAddRev);
    VGSvcWriteProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestAdd/Version",
                   RT_SUCCESS(rc) ? pszAddVer    : VBOX_VERSION_STRING_RAW);
    VGSvcWriteProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestAdd/VersionExt",
                   RT_SUCCESS(rc) ? pszAddVerExt : VBOX_VERSION_STRING);
    VGSvcWriteProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestAdd/Revision",
                   RT_SUCCESS(rc) ? pszAddRev    : RT_XSTR(VBOX_SVN_REV));
    if (RT_SUCCESS(rc))
    {
        RTStrFree(pszAddVer);
        RTStrFree(pszAddVerExt);
        RTStrFree(pszAddRev);
    }

#ifdef RT_OS_WINDOWS
    /*
     * Do windows specific properties.
     */
    char *pszInstDir = NULL;
    rc = VbglR3QueryAdditionsInstallationPath(&pszInstDir);
    VGSvcWriteProp(&g_VMInfoGuestPropSvcClient, "/VirtualBox/GuestAdd/InstallDir", RT_SUCCESS(rc) ? pszInstDir : "");
    if (RT_SUCCESS(rc))
        RTStrFree(pszInstDir);

    VGSvcVMInfoWinWriteComponentVersions(&g_VMInfoGuestPropSvcClient);
#endif
}


#if !defined(RT_OS_WINDOWS) && !defined(RT_OS_OS2) && !defined(RT_OS_FREEBSD) && !defined(RT_OS_HAIKU)
/*
 * Add a user to the list of active users (while ignoring duplicates
 * and dynamically maintaining the list storage)
 */
# define USER_LIST_CHUNK_SIZE 32
#endif
/** @todo wtf? */
static uint32_t cUsersInList;
#if !defined(RT_OS_WINDOWS) && !defined(RT_OS_OS2) && !defined(RT_OS_FREEBSD) && !defined(RT_OS_HAIKU)
static uint32_t cListSize;
static char **papszUsers;

static void vgsvcVMInfoAddUserToList(const char *name, const char *src)
{
    int rc;
    bool fFound = false;
    for (uint32_t idx = 0; idx < cUsersInList && !fFound; idx++)
        fFound = strncmp(papszUsers[idx], name, 32) == 0;
    VGSvcVerbose(5, "LoggedInUsers: Asked to add user '%s' from '%s' to list (already in list = %lu)\n", name, src, fFound);
    if (!fFound)
    {
        if (cUsersInList + 1 > cListSize)
        {
            VGSvcVerbose(5, "LoggedInUsers: increase user list size from %lu to %lu\n", cListSize, cListSize + USER_LIST_CHUNK_SIZE);
            cListSize += USER_LIST_CHUNK_SIZE;
            void *pvNew = RTMemRealloc(papszUsers, cListSize * sizeof(char*));
            AssertReturnVoidStmt(pvNew, cListSize -= USER_LIST_CHUNK_SIZE);
            papszUsers = (char **)pvNew;
        }
        VGSvcVerbose(4, "LoggedInUsers: Adding user '%s' from '%s' to list (size = %lu, count = %lu)\n", name, src, cListSize, cUsersInList);
        rc = RTStrDupEx(&papszUsers[cUsersInList], name);
        if (!RT_FAILURE(rc))
            cUsersInList++;
    }
}
#endif


#if defined(VBOX_WITH_DBUS) && defined(RT_OS_LINUX) /* Not yet for Solaris/FreeBSD. */

/*
 * Simple wrappers to work around compiler-specific va_list madness.
 */
static dbus_bool_t vboxService_dbus_message_get_args(DBusMessage *message, DBusError *error, int first_arg_type, ...)
{
    va_list va;
    va_start(va, first_arg_type);
    dbus_bool_t ret = dbus_message_get_args_valist(message, error, first_arg_type, va);
    va_end(va);
    return ret;
}

static dbus_bool_t vboxService_dbus_message_append_args(DBusMessage *message, int first_arg_type, ...)
{
    va_list va;
    va_start(va, first_arg_type);
    dbus_bool_t ret = dbus_message_append_args_valist(message, first_arg_type, va);
    va_end(va);
    return ret;
}

# ifndef DBUS_TYPE_VARIANT
#  define DBUS_TYPE_VARIANT      ((int) 'v')
# endif
/*
 * Wrapper to dig values out of dbus replies, which are contained in
 * a 'variant' and must be iterated into twice.
 *
 * Returns true if it thinks it got a value; false if not.
 *
 * This does various error checking so the caller can skip it:
 *   - whether a DBusError is set
 *   - whether the DBusMessage is valid
 *   - whether we actually got a 'variant'
 *   - whether we got the type the caller's looking for
 */
static bool vboxService_dbus_unpack_variant_reply(DBusError *error, DBusMessage *pReply, char pType, void *pValue)
{
    if (dbus_error_is_set(error))
    {
        VGSvcError("dbus_unpack_variant_reply: dbus returned error '%s'\n", error->message);
        dbus_error_free(error);
    }
    else if (pReply)
    {
        DBusMessageIter iterMsg;
        int             iterType;
        dbus_message_iter_init(pReply, &iterMsg);
        iterType = dbus_message_iter_get_arg_type(&iterMsg);
        if (iterType == DBUS_TYPE_VARIANT)
        {
            DBusMessageIter iterValueMsg;
            int             iterValueType;
            dbus_message_iter_recurse(&iterMsg, &iterValueMsg);
            iterValueType = dbus_message_iter_get_arg_type(&iterValueMsg);
            if (iterValueType == pType)
            {
                dbus_message_iter_get_basic(&iterValueMsg, pValue);
                return true;
            }
        }
    }
    return false;
}

/*
 * Wrapper to NULL out the DBusMessage pointer while discarding it.
 * DBus API is multi-threaded and can have multiple concurrent accessors.
 * Our use here is single-threaded and can never have multiple accessors.
 */
static void vboxService_dbus_message_discard(DBusMessage **ppMsg)
{
    if (ppMsg && *ppMsg)
    {
        /** @todo any clean-ish way to verify DBus internal refcount == 1 here? */
        dbus_message_unref(*ppMsg);
        *ppMsg = NULL;
    }
}

static void vgsvcVMInfoDBusAddToUserList(void)
{
# ifdef VBOX_WITH_DBUS
#  if defined(RT_OS_LINUX) /* Not yet for Solaris/FreeBSB. */
    DBusError dbErr;
    DBusConnection *pConnection = NULL;
    int rc2 = RTDBusLoadLib();
    bool fHaveLibDbus = false;
    if (RT_SUCCESS(rc2))
    {
        /* Handle desktop sessions using systemd-logind. */
        VGSvcVerbose(4, "Checking systemd-logind sessions ...\n");
        fHaveLibDbus = true;
        dbus_error_init(&dbErr);
        pConnection = dbus_bus_get(DBUS_BUS_SYSTEM, &dbErr);
    }

    if (   pConnection
        && !dbus_error_is_set(&dbErr))
    {
/** @todo is there some Less Horrible Way(tm) to access dbus? */
        /* Get all available sessions. */
        /* like `busctl call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager ListSessions` */
        DBusMessage *pMsgSessions = dbus_message_new_method_call(SYSTEMD_LOGIN_INTERFACE,
                                                                 SYSTEMD_LOGIN_PATH,
                                                                 SYSTEMD_LOGIN_MANAGER_INTERFACE,
                                                                 "ListSessions");
        if (   pMsgSessions
            && dbus_message_get_type(pMsgSessions) == DBUS_MESSAGE_TYPE_METHOD_CALL)
        {
            DBusMessage *pReplySessions = dbus_connection_send_with_reply_and_block(pConnection,
                                                                                    pMsgSessions, 30 * 1000 /* 30s timeout */,
                                                                                    &dbErr);
            if (   pReplySessions
                && !dbus_error_is_set(&dbErr))
            {
                /* dbus_message_new_method_call() returns a DBusMessage, which we must iterate to get the returned value */
                DBusMessageIter messageIterMsg;
                int             messageIterType;
                dbus_message_iter_init(pReplySessions, &messageIterMsg);
                while ((messageIterType = dbus_message_iter_get_arg_type (&messageIterMsg)) != DBUS_TYPE_INVALID)
                {
                    if (messageIterType == DBUS_TYPE_ARRAY)
                    {
                        /* "ListSessions" returns an array, which we must iterate to get the array elements */
                        DBusMessageIter arrayIterMsg;
                        int             arrayIterType;
                        dbus_message_iter_recurse(&messageIterMsg, &arrayIterMsg);
                        while ((arrayIterType = dbus_message_iter_get_arg_type (&arrayIterMsg)) != DBUS_TYPE_INVALID)
                        {
                            if (arrayIterType == DBUS_TYPE_STRUCT)
                            {
                                /* The array elements are structs, which we must iterate to get the struct elements */
                                DBusMessageIter structIterMsg;
                                int             structIterType;
                                dbus_message_iter_recurse(&arrayIterMsg, &structIterMsg);
                                while ((structIterType = dbus_message_iter_get_arg_type (&structIterMsg)) != DBUS_TYPE_INVALID)
                                {
                                    if (structIterType == DBUS_TYPE_OBJECT_PATH)
                                    {
                                        /* We are interested only in the "object path" struct element */
                                        const char *objectPath;
                                        dbus_message_iter_get_basic(&structIterMsg, &objectPath);
                                        const char *pInterface = SYSTEMD_LOGIN_SESSION_INTERFACE;
                                        /* Create and send a new dbus query asking for that session's details */
                                        DBusMessage *pMsgSession = dbus_message_new_method_call(SYSTEMD_LOGIN_INTERFACE,
                                                                                                objectPath,
                                                                                                "org.freedesktop.DBus.Properties",
                                                                                                "Get");
                                        if (   pMsgSession
                                            && dbus_message_get_type(pMsgSession) == DBUS_MESSAGE_TYPE_METHOD_CALL)
                                            {
                                            const char *pPropertyActive = "Active";
                                            vboxService_dbus_message_append_args(pMsgSession,
                                                                                 DBUS_TYPE_STRING, &pInterface,
                                                                                 DBUS_TYPE_STRING, &pPropertyActive,
                                                                                 DBUS_TYPE_INVALID, 0);
                                            /* like `busctl get-property org.freedesktop.login1 %s org.freedesktop.login1.Session Active` %(objectPath) */
                                            DBusMessage *pReplySession = dbus_connection_send_with_reply_and_block(
                                                                             pConnection,
                                                                             pMsgSession,
                                                                             -1,
                                                                             &dbErr);
                                            int sessionPropertyActiveValue;
                                            if (   vboxService_dbus_unpack_variant_reply(
                                                       &dbErr,
                                                       pReplySession,
                                                       DBUS_TYPE_BOOLEAN,
                                                       &sessionPropertyActiveValue)
                                                && sessionPropertyActiveValue)
                                                {
                                                DBusMessage *pMsgSession2 = dbus_message_new_method_call(SYSTEMD_LOGIN_INTERFACE,
                                                                                                         objectPath,
                                                                                                         "org.freedesktop.DBus.Properties",
                                                                                                         "Get");
                                                const char *pPropertyName = "Name";
                                                if (   pMsgSession2
                                                    && dbus_message_get_type(pMsgSession2) == DBUS_MESSAGE_TYPE_METHOD_CALL)
                                                    {
                                                    vboxService_dbus_message_append_args(pMsgSession2,
                                                                                         DBUS_TYPE_STRING, &pInterface,
                                                                                         DBUS_TYPE_STRING, &pPropertyName,
                                                                                         DBUS_TYPE_INVALID, 0);
                                                    /* like `busctl get-property org.freedesktop.login1 %s org.freedesktop.login1.Session Name` %(objectPath) */
                                                    DBusMessage *pReplyName = dbus_connection_send_with_reply_and_block(
                                                                                 pConnection,
                                                                                 pMsgSession2,
                                                                                 -1,
                                                                                 &dbErr);
                                                    const char *sessionPropertyNameValue;
                                                    if (   vboxService_dbus_unpack_variant_reply(
                                                               &dbErr,
                                                               pReplyName,
                                                               DBUS_TYPE_STRING,
                                                               &sessionPropertyNameValue)
                                                        && sessionPropertyNameValue)
                                                        vgsvcVMInfoAddUserToList(sessionPropertyNameValue, "systemd-logind");
                                                    vboxService_dbus_message_discard(&pReplyName);
                                                }
                                                vboxService_dbus_message_discard(&pMsgSession2);
                                            }
                                            vboxService_dbus_message_discard(&pReplySession);
                                        }
                                        vboxService_dbus_message_discard(&pMsgSession);
                                    }
                                    dbus_message_iter_next (&structIterMsg);
                                }
                            }
                            dbus_message_iter_next (&arrayIterMsg);
                        }
                    }
                    dbus_message_iter_next (&messageIterMsg);
                }
                vboxService_dbus_message_discard(&pReplySessions);
            }
        }
        else
        {
            static int s_iBitchedAboutSystemdLogind = 0;
            if (s_iBitchedAboutSystemdLogind < 3)
            {
                s_iBitchedAboutSystemdLogind++;
                VGSvcError("Unable to invoke systemd-logind (%d/3) -- maybe not installed / used? Error: %s\n",
                           s_iBitchedAboutSystemdLogind,
                           dbus_error_is_set(&dbErr) ? dbErr.message : "No error information available");
            }
        }

        vboxService_dbus_message_discard(&pMsgSessions);
        if (dbus_error_is_set(&dbErr))
            dbus_error_free(&dbErr);
    }
    if (RT_SUCCESS(rc2))
    {
        /* Handle desktop sessions using ConsoleKit. */
        VGSvcVerbose(4, "Checking ConsoleKit sessions ...\n");
        fHaveLibDbus = true;
        dbus_error_init(&dbErr);
        /** @todo should this be dbus_connection_open() (and below, dbus_connection_unref())? */
        pConnection = dbus_bus_get(DBUS_BUS_SYSTEM, &dbErr);
    }

    if (   pConnection
        && !dbus_error_is_set(&dbErr))
    {
        /* Get all available sessions. */
        DBusMessage *pMsgSessions = dbus_message_new_method_call(CK_INTERFACE,
                                                                 CK_MANAGER_PATH,
                                                                 CK_MANAGER_INTERFACE,
                                                                 "GetSessions");
        if (   pMsgSessions
            && dbus_message_get_type(pMsgSessions) == DBUS_MESSAGE_TYPE_METHOD_CALL)
        {
            DBusMessage *pReplySessions = dbus_connection_send_with_reply_and_block(pConnection,
                                                                                    pMsgSessions, 30 * 1000 /* 30s timeout */,
                                                                                    &dbErr);
            if (   pReplySessions
                && !dbus_error_is_set(&dbErr))
            {
                char **ppszSessions;
                int cSessions;
                if (   dbus_message_get_type(pMsgSessions) == DBUS_MESSAGE_TYPE_METHOD_CALL
                    && vboxService_dbus_message_get_args(pReplySessions, &dbErr, DBUS_TYPE_ARRAY,
                                                         DBUS_TYPE_OBJECT_PATH, &ppszSessions, &cSessions,
                                                         DBUS_TYPE_INVALID /* Termination */))
                {
                    VGSvcVerbose(4, "ConsoleKit: retrieved %RU16 session(s)\n", cSessions);

                    char **ppszCurSession = ppszSessions;
                    for (ppszCurSession; ppszCurSession && *ppszCurSession; ppszCurSession++)
                    {
                        VGSvcVerbose(4, "ConsoleKit: processing session '%s' ...\n", *ppszCurSession);

                        /* Only respect active sessions .*/
                        bool fActive = false;
                        DBusMessage *pMsgSessionActive = dbus_message_new_method_call(CK_INTERFACE,
                                                                                      *ppszCurSession,
                                                                                      CK_SESSION_INTERFACE,
                                                                                      "IsActive");
                        if (   pMsgSessionActive
                            && dbus_message_get_type(pMsgSessionActive) == DBUS_MESSAGE_TYPE_METHOD_CALL)
                        {
                            DBusMessage *pReplySessionActive = dbus_connection_send_with_reply_and_block(pConnection,
                                                                                                         pMsgSessionActive,
                                                                                                         30 * 1000 /*sec*/,
                                                                                                         &dbErr);
                            if (   pReplySessionActive
                                && !dbus_error_is_set(&dbErr))
                            {
                                DBusMessageIter itMsg;
                                if (   dbus_message_iter_init(pReplySessionActive, &itMsg)
                                    && dbus_message_iter_get_arg_type(&itMsg) == DBUS_TYPE_BOOLEAN)
                                {
                                    /* Get uid from message. */
                                    int val;
                                    dbus_message_iter_get_basic(&itMsg, &val);
                                    fActive = val >= 1;
                                }

                            }
                            /** @todo clean up if &dbErr */
                            vboxService_dbus_message_discard(&pReplySessionActive);

                            vboxService_dbus_message_discard(&pMsgSessionActive);
                        }

                        VGSvcVerbose(4, "ConsoleKit: session '%s' is %s\n",
                                           *ppszCurSession, fActive ? "active" : "not active");

                        /* *ppszCurSession now contains the object path
                         * (e.g. "/org/freedesktop/ConsoleKit/Session1"). */
                        DBusMessage *pMsgUnixUser = dbus_message_new_method_call(CK_INTERFACE,
                                                                                 *ppszCurSession,
                                                                                 CK_SESSION_INTERFACE,
                                                                                 "GetUnixUser");
                        if (   fActive
                            && pMsgUnixUser
                            && dbus_message_get_type(pMsgUnixUser) == DBUS_MESSAGE_TYPE_METHOD_CALL)
                        {
                            DBusMessage *pReplyUnixUser = dbus_connection_send_with_reply_and_block(pConnection,
                                                                                                    pMsgUnixUser,
                                                                                                    30 * 1000 /* 30s timeout */,
                                                                                                    &dbErr);
                            if (   pReplyUnixUser
                                && !dbus_error_is_set(&dbErr))
                            {
                                DBusMessageIter itMsg;
                                if (   dbus_message_iter_init(pReplyUnixUser, &itMsg)
                                    && dbus_message_iter_get_arg_type(&itMsg) == DBUS_TYPE_UINT32)
                                {
                                    /* Get uid from message. */
                                    uint32_t uid;
                                    dbus_message_iter_get_basic(&itMsg, &uid);

                                    /* Look up user name (realname) from uid. */
                                    setpwent();
                                    struct passwd *ppwEntry = getpwuid(uid);
                                    if (   ppwEntry
                                        && ppwEntry->pw_name)
                                    {
                                            VGSvcVerbose(4, "ConsoleKit: session '%s' -> %s (uid: %RU32)\n",
                                                         *ppszCurSession, ppwEntry->pw_name, uid);
                                            vgsvcVMInfoAddUserToList(ppwEntry->pw_name, "ConsoleKit");
                                    }
                                    else
                                        VGSvcError("ConsoleKit: unable to lookup user name for uid=%RU32\n", uid);
                                }
                                else
                                    AssertMsgFailed(("ConsoleKit: GetUnixUser returned a wrong argument type\n"));
                            }
                            /** @todo clean up if &dbErr */

                            vboxService_dbus_message_discard(&pReplyUnixUser);
                        }
                        else if (fActive) /* don't bitch about inactive users */
                        {
                            static int s_iBitchedAboutConsoleKit = 0;
                            if (s_iBitchedAboutConsoleKit < 1)
                            {
                                s_iBitchedAboutConsoleKit++;
                                VGSvcError("ConsoleKit: unable to retrieve user for session '%s' (msg type=%d): %s\n",
                                           *ppszCurSession, dbus_message_get_type(pMsgUnixUser),
                                           dbus_error_is_set(&dbErr) ? dbErr.message : "No error information available");
                            }
                        }

                        vboxService_dbus_message_discard(&pMsgUnixUser);
                    }

                    dbus_free_string_array(ppszSessions);
                }
                else
                    VGSvcError("ConsoleKit: unable to retrieve session parameters (msg type=%d): %s\n",
                               dbus_message_get_type(pMsgSessions),
                               dbus_error_is_set(&dbErr) ? dbErr.message : "No error information available");
                vboxService_dbus_message_discard(&pReplySessions);
            }
        }
        else
        {
            static int s_iBitchedAboutConsoleKit = 0;
            if (s_iBitchedAboutConsoleKit < 3)
            {
                s_iBitchedAboutConsoleKit++;
                VGSvcError("Unable to invoke ConsoleKit (%d/3) -- maybe not installed / used? Error: %s\n",
                           s_iBitchedAboutConsoleKit,
                           dbus_error_is_set(&dbErr) ? dbErr.message : "No error information available");
            }
        }

        vboxService_dbus_message_discard(&pMsgSessions);
    }
    else
    {
        static int s_iBitchedAboutDBus = 0;
        if (s_iBitchedAboutDBus < 3)
        {
            s_iBitchedAboutDBus++;
            VGSvcError("Unable to connect to system D-Bus (%d/3): %s\n", s_iBitchedAboutDBus,
                       fHaveLibDbus && dbus_error_is_set(&dbErr) ? dbErr.message : "D-Bus not installed");
        }
    }

    if (   fHaveLibDbus
        && dbus_error_is_set(&dbErr))
        dbus_error_free(&dbErr);
#  endif /* RT_OS_LINUX */
# endif /* VBOX_WITH_DBUS */

}

#endif /* VBOX_WITH_DBUS && RT_OS_LINUX */


/**
 * Provide information about active users.
 */
static int vgsvcVMInfoWriteUsers(void)
{
    /*
     * Get the number of logged in users and their names (comma separated list).
     */
    char *pszUserList = NULL;
    cUsersInList = 0;

#ifdef RT_OS_WINDOWS
    /* We're passing &g_VMInfoPropCache to this function, however, it's only
       ever used to call back into VGSvcVMInfoUpdateUserF and VGSvcVMInfoUpdateUserV (which
       doesn't technically need them). */
    int rc = VGSvcVMInfoWinQueryUserListAndUpdateInfo(&g_VMInfoPropCache, &pszUserList, &cUsersInList);

#elif defined(RT_OS_FREEBSD)
    /** @todo FreeBSD: Port logged on user info retrieval.
     *                 However, FreeBSD 9 supports utmpx, so we could use the code
     *                 block below (?). */
    int rc = VERR_NOT_IMPLEMENTED;

#elif defined(RT_OS_HAIKU)
    /** @todo Haiku: Port logged on user info retrieval. */
    int rc = VERR_NOT_IMPLEMENTED;

#elif defined(RT_OS_OS2)
    /** @todo OS/2: Port logged on (LAN/local/whatever) user info retrieval. */
    int rc = VERR_NOT_IMPLEMENTED;

#else
    setutxent();
    utmpx *ut_user;
    cListSize = USER_LIST_CHUNK_SIZE;

    /* Allocate a first array to hold 32 users max. */
    papszUsers = (char **)RTMemAllocZ(cListSize * sizeof(char *));
    int rc = papszUsers ? VINF_SUCCESS : VERR_NO_MEMORY;

    /* Process all entries in the utmp file.
     * Note: This only handles */
    while (   (ut_user = getutxent())
           && RT_SUCCESS(rc))
    {
# ifdef RT_OS_DARWIN /* No ut_user->ut_session on Darwin */
        VGSvcVerbose(4, "Found entry '%s' (type: %d, PID: %RU32)\n", ut_user->ut_user, ut_user->ut_type, ut_user->ut_pid);
# else
        VGSvcVerbose(4, "Found entry '%s' (type: %d, PID: %RU32, session: %RU32)\n",
                     ut_user->ut_user, ut_user->ut_type, ut_user->ut_pid, ut_user->ut_session);
# endif

        /* Make sure we don't add user names which are not
         * part of type USER_PROCESS. */
        if (ut_user->ut_type == USER_PROCESS) /* Regular user process. */
            vgsvcVMInfoAddUserToList(ut_user->ut_user, "utmpx");
    }

# if defined(VBOX_WITH_DBUS) && defined(RT_OS_LINUX) /* Not yet for Solaris/FreeBSD. */
    vgsvcVMInfoDBusAddToUserList();
# endif

    /* Calc the string length. */
    size_t cchUserList = 0;
    if (RT_SUCCESS(rc))
        for (uint32_t i = 0; i < cUsersInList; i++)
            cchUserList += (i != 0) + strlen(papszUsers[i]);

    /* Build the user list. */
    if (cchUserList > 0)
    {
        if (RT_SUCCESS(rc))
            rc = RTStrAllocEx(&pszUserList, cchUserList + 1);
        if (RT_SUCCESS(rc))
        {
            char *psz = pszUserList;
            for (uint32_t i = 0; i < cUsersInList; i++)
            {
                if (i != 0)
                    *psz++ = ',';
                size_t cch = strlen(papszUsers[i]);
                memcpy(psz, papszUsers[i], cch);
                psz += cch;
            }
            *psz = '\0';
        }
    }

    /* Cleanup. */
    for (uint32_t i = 0; i < cUsersInList; i++)
        RTStrFree(papszUsers[i]);
    RTMemFree(papszUsers);

    endutxent(); /* Close utmpx file. */
#endif /* !RT_OS_WINDOWS && !RT_OS_FREEBSD && !RT_OS_HAIKU && !RT_OS_OS2 */

    Assert(RT_FAILURE(rc) || cUsersInList == 0 || (pszUserList && *pszUserList));

    /*
     * If the user enumeration above failed, reset the user count to 0 except
     * if we didn't have enough memory anymore. In that case we want to preserve
     * the previous user count in order to not confuse third party tools which
     * rely on that count.
     */
    if (RT_FAILURE(rc))
    {
        if (rc == VERR_NO_MEMORY)
        {
            static int s_iVMInfoBitchedOOM = 0;
            if (s_iVMInfoBitchedOOM++ < 3)
                VGSvcVerbose(0, "Warning: Not enough memory available to enumerate users! Keeping old value (%RU32)\n",
                             g_cVMInfoLoggedInUsers);
            cUsersInList = g_cVMInfoLoggedInUsers;
        }
        else
            cUsersInList = 0;
    }
    else /* Preserve logged in users count. */
        g_cVMInfoLoggedInUsers = cUsersInList;

    VGSvcVerbose(4, "cUsersInList=%RU32, pszUserList=%s, rc=%Rrc\n", cUsersInList, pszUserList ? pszUserList : "<NULL>", rc);

    AssertMsg(!pszUserList || cUsersInList, ("pszUserList contains users whereas cUsersInList is 0: %s\n", pszUserList));
    rc = VGSvcPropCacheUpdate(&g_VMInfoPropCache, g_pszPropCacheValLoggedInUsersList, pszUserList);
    if (RT_FAILURE(rc))
        VGSvcError("Error writing logged in users list, rc=%Rrc\n", rc);

    rc = VGSvcPropCacheUpdate(&g_VMInfoPropCache, g_pszPropCacheValNoLoggedInUsers, cUsersInList == 0 ? "true" : "false");
    if (RT_FAILURE(rc))
        VGSvcError("Error writing no logged in users, rc=%Rrc\n", rc);

    /* (This is the operation which return code counts and must be returned.) */
    rc = VGSvcPropCacheUpdateF(&g_VMInfoPropCache, g_pszPropCacheValLoggedInUsers, "%RU32", cUsersInList);
    if (RT_FAILURE(rc))
        VGSvcError("Error writing logged in users count (beacon), rc=%Rrc\n", rc);

    if (pszUserList)
        RTStrFree(pszUserList);

    VGSvcVerbose(4, "Writing users returned with rc=%Rrc\n", rc);
    return rc;
}


/**
 * Provide information about the guest network.
 */
static int vgsvcVMInfoWriteNetwork(void)
{
    uint32_t    cIfsReported = 0;
    char        szPropPath[256];

#ifdef RT_OS_WINDOWS
    /*
     * Check that the APIs we need are present.
     */
    if (   !g_pfnWSAIoctl
        || !g_pfnWSASocketA
        || !g_pfnWSAGetLastError
        || !g_pfninet_ntoa
        || !g_pfnclosesocket)
        return VINF_SUCCESS;

    /*
     * Query the IP adapter info first, if we have the API.
     */
    IP_ADAPTER_INFO *pAdpInfo  = NULL;
    if (g_pfnGetAdaptersInfo)
    {
        ULONG cbAdpInfo = RT_MAX(sizeof(IP_ADAPTER_INFO) * 2, _2K);
        pAdpInfo  = (IP_ADAPTER_INFO *)RTMemAllocZ(cbAdpInfo);
        if (!pAdpInfo)
        {
            VGSvcError("VMInfo/Network: Failed to allocate two IP_ADAPTER_INFO structures\n");
            return VERR_NO_MEMORY;
        }

        DWORD dwRet = g_pfnGetAdaptersInfo(pAdpInfo, &cbAdpInfo);
        if (dwRet == ERROR_BUFFER_OVERFLOW)
        {
            IP_ADAPTER_INFO *pAdpInfoNew = (IP_ADAPTER_INFO*)RTMemRealloc(pAdpInfo, cbAdpInfo);
            if (pAdpInfoNew)
            {
                pAdpInfo = pAdpInfoNew;
                RT_BZERO(pAdpInfo, cbAdpInfo);
                dwRet = g_pfnGetAdaptersInfo(pAdpInfo, &cbAdpInfo);
            }
        }
        if (dwRet != NO_ERROR)
        {
            RTMemFree(pAdpInfo);
            pAdpInfo  = NULL;
            if (dwRet == ERROR_NO_DATA)
                /* If no network adapters available / present in the
                   system we pretend success to not bail out too early. */
                VGSvcVerbose(3, "VMInfo/Network: No network adapters present according to GetAdaptersInfo.\n");
            else
            {
                VGSvcError("VMInfo/Network: Failed to get adapter info: Error %d\n", dwRet);
                return RTErrConvertFromWin32(dwRet);
            }
        }
    }

    /*
     * Ask the TCP/IP stack for an interface list.
     */
    SOCKET sd = g_pfnWSASocketA(AF_INET, SOCK_DGRAM, 0, 0, 0, 0);
    if (sd == SOCKET_ERROR) /* Socket invalid. */
    {
        int const wsaErr = g_pfnWSAGetLastError();
        RTMemFree(pAdpInfo);

        /* Don't complain/bail out with an error if network stack is not up; can happen
         * on NT4 due to start up when not connected shares dialogs pop up. */
        if (wsaErr == WSAENETDOWN)
        {
            VGSvcVerbose(0, "VMInfo/Network: Network is not up yet.\n");
            return VINF_SUCCESS;
        }
        VGSvcError("VMInfo/Network: Failed to get a socket: Error %d\n", wsaErr);
        return RTErrConvertFromWin32(wsaErr);
    }

    INTERFACE_INFO  aInterfaces[20] = {{0}};
    DWORD           cbReturned      = 0;
# ifdef RT_ARCH_X86
    /* Workaround for uninitialized variable used in memcpy in GetTcpipInterfaceList
       (NT4SP1 at least).  It seems to be happy enough with garbages, no failure
       returns so far, so we just need to prevent it from crashing by filling the
       stack with valid pointer values prior to the API call. */
    _asm
    {
        mov     edx, edi
        lea     eax, aInterfaces
        mov     [esp - 0x1000], eax
        mov     [esp - 0x2000], eax
        mov     ecx, 0x2000/4 - 1
        cld
        lea     edi, [esp - 0x2000]
        rep stosd
        mov     edi, edx
    }
# endif
    int rc = g_pfnWSAIoctl(sd,
                           SIO_GET_INTERFACE_LIST,
                           NULL,                /* pvInBuffer */
                           0,                   /* cbInBuffer */
                           &aInterfaces[0],     /* pvOutBuffer */
                           sizeof(aInterfaces), /* cbOutBuffer */
                           &cbReturned,
                           NULL,                /* pOverlapped */
                           NULL);               /* pCompletionRoutine */
    if (rc == SOCKET_ERROR)
    {
        VGSvcError("VMInfo/Network: Failed to WSAIoctl() on socket: Error: %d\n", g_pfnWSAGetLastError());
        RTMemFree(pAdpInfo);
        g_pfnclosesocket(sd);
        return RTErrConvertFromWin32(g_pfnWSAGetLastError());
    }
    g_pfnclosesocket(sd);
    int cIfacesSystem = cbReturned / sizeof(INTERFACE_INFO);

    /*
     * Iterate the inteface list we got back from the TCP/IP,
     * using the pAdpInfo list to supply the MAC address.
     */
    /** @todo Use GetAdaptersInfo() and GetAdapterAddresses (IPv4 + IPv6) for more information. */
    for (int i = 0; i < cIfacesSystem; ++i)
    {
        if (aInterfaces[i].iiFlags & IFF_LOOPBACK) /* Skip loopback device. */
            continue;
        sockaddr_in *pAddress = &aInterfaces[i].iiAddress.AddressIn;
        char szIp[32];
        RTStrPrintf(szIp, sizeof(szIp), "%s", g_pfninet_ntoa(pAddress->sin_addr)); /* (Keep a copy for the MAC lookup below.) */
        RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/V4/IP", cIfsReported);
        VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, szIp);

        pAddress = &aInterfaces[i].iiBroadcastAddress.AddressIn;
        RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/V4/Broadcast", cIfsReported);
        VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, g_pfninet_ntoa(pAddress->sin_addr));

        pAddress = (sockaddr_in *)&aInterfaces[i].iiNetmask;
        RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/V4/Netmask", cIfsReported);
        VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, g_pfninet_ntoa(pAddress->sin_addr));

        RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/Status", cIfsReported);
        VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, aInterfaces[i].iiFlags & IFF_UP ? "Up" : "Down");

        RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/MAC", cIfsReported);
        IP_ADAPTER_INFO *pAdp;
        for (pAdp = pAdpInfo; pAdp; pAdp = pAdp->Next)
            if (!strcmp(pAdp->IpAddressList.IpAddress.String, szIp))
                break;
        if (pAdp)
            VGSvcPropCacheUpdateF(&g_VMInfoPropCache, szPropPath, "%02X%02X%02X%02X%02X%02X",
                                  pAdp->Address[0], pAdp->Address[1], pAdp->Address[2],
                                  pAdp->Address[3], pAdp->Address[4], pAdp->Address[5]);
        else
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, NULL);

        cIfsReported++;
    }

    RTMemFree(pAdpInfo);

#elif defined(RT_OS_HAIKU)
    /** @todo Haiku: implement network info. retreival */
    return VERR_NOT_IMPLEMENTED;

#elif defined(RT_OS_DARWIN) || defined(RT_OS_FREEBSD) || defined(RT_OS_NETBSD)
    struct ifaddrs *pIfHead = NULL;

    /* Get all available interfaces */
    int rc = getifaddrs(&pIfHead);
    if (rc < 0)
    {
        rc = RTErrConvertFromErrno(errno);
        VGSvcError("VMInfo/Network: Failed to get all interfaces: Error %Rrc\n");
        return rc;
    }

    /* Loop through all interfaces and set the data. */
    for (struct ifaddrs *pIfCurr = pIfHead; pIfCurr; pIfCurr = pIfCurr->ifa_next)
    {
        /*
         * Only AF_INET and no loopback interfaces
         */
        /** @todo IPv6 interfaces */
        if (   pIfCurr->ifa_addr->sa_family == AF_INET
            && !(pIfCurr->ifa_flags & IFF_LOOPBACK))
        {
            char szInetAddr[NI_MAXHOST];

            memset(szInetAddr, 0, NI_MAXHOST);
            getnameinfo(pIfCurr->ifa_addr, sizeof(struct sockaddr_in),
                        szInetAddr, NI_MAXHOST, NULL, 0, NI_NUMERICHOST);
            RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/V4/IP", cIfsReported);
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, szInetAddr);

            memset(szInetAddr, 0, NI_MAXHOST);
            getnameinfo(pIfCurr->ifa_broadaddr, sizeof(struct sockaddr_in),
                        szInetAddr, NI_MAXHOST, NULL, 0, NI_NUMERICHOST);
            RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/V4/Broadcast", cIfsReported);
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, szInetAddr);

            memset(szInetAddr, 0, NI_MAXHOST);
            getnameinfo(pIfCurr->ifa_netmask, sizeof(struct sockaddr_in),
                        szInetAddr, NI_MAXHOST, NULL, 0, NI_NUMERICHOST);
            RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/V4/Netmask", cIfsReported);
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, szInetAddr);

            /* Search for the AF_LINK interface of the current AF_INET one and get the mac. */
            RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/MAC", cIfsReported);
            uint8_t const *pu8Mac = NULL;
            for (struct ifaddrs *pIfLinkCurr = pIfHead; pIfLinkCurr; pIfLinkCurr = pIfLinkCurr->ifa_next)
                if (   pIfLinkCurr->ifa_addr->sa_family == AF_LINK
                    && !strcmp(pIfCurr->ifa_name, pIfLinkCurr->ifa_name))
                {
                    struct sockaddr_dl *pLinkAddress = (struct sockaddr_dl *)pIfLinkCurr->ifa_addr;
                    AssertPtr(pLinkAddress);
                    pu8Mac = (uint8_t const *)LLADDR(pLinkAddress);
                    AssertPtr(pu8Mac);
                    break;
                }
            if (pu8Mac)
                VGSvcPropCacheUpdateF(&g_VMInfoPropCache, szPropPath, "%02X%02X%02X%02X%02X%02X",
                                      pu8Mac[0], pu8Mac[1], pu8Mac[2], pu8Mac[3],  pu8Mac[4], pu8Mac[5]);
            else
                VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, NULL);

            RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32/Status", cIfsReported);
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, pIfCurr->ifa_flags & IFF_UP ? "Up" : "Down");

            cIfsReported++;
        }
    }

    /* Free allocated resources. */
    freeifaddrs(pIfHead);

#else /* !RT_OS_WINDOWS && !RT_OS_FREEBSD */
    /*
     * Use SIOCGIFCONF to get a list of interface/protocol configurations.
     *
     * See "UNIX Network Programming Volume 1" by W. R. Stevens, section 17.6
     * for details on this ioctl.
     */
    int sd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sd < 0)
    {
        int rc = RTErrConvertFromErrno(errno);
        VGSvcError("VMInfo/Network: Failed to get a socket: Error %Rrc\n", rc);
        return rc;
    }

    /* Call SIOCGIFCONF with the right sized buffer (remember the size). */
    static int      s_cbBuf = 256; // 1024
    int             cbBuf   = s_cbBuf;
    char           *pchBuf;
    struct ifconf   IfConf;
    int rc = VINF_SUCCESS;
    for (;;)
    {
        pchBuf = (char *)RTMemTmpAllocZ(cbBuf);
        if (!pchBuf)
        {
            rc = VERR_NO_TMP_MEMORY;
            break;
        }

        IfConf.ifc_len = cbBuf;
        IfConf.ifc_buf = pchBuf;
        if (ioctl(sd, SIOCGIFCONF, &IfConf) >= 0)
        {
            /* Hard to anticipate how space an address might possibly take, so
               making some generous assumptions here to avoid performing the
               query twice with different buffer sizes. */
            if (IfConf.ifc_len + 128 < cbBuf)
                break;
        }
        else if (errno != EOVERFLOW)
        {
            rc = RTErrConvertFromErrno(errno);
            break;
        }

        /* grow the buffer */
        s_cbBuf = cbBuf *= 2;
        RTMemFree(pchBuf);
    }
    if (RT_FAILURE(rc))
    {
        close(sd);
        RTMemTmpFree(pchBuf);
        VGSvcError("VMInfo/Network: Error doing SIOCGIFCONF (cbBuf=%d): %Rrc\n", cbBuf, rc);
        return rc;
    }

    /*
     * Iterate the interface/protocol configurations.
     *
     * Note! The current code naively assumes one IPv4 address per interface.
     *       This means that guest assigning more than one address to an
     *       interface will get multiple entries for one physical interface.
     */
# ifdef RT_OS_OS2
    struct ifreq   *pPrevLinkAddr = NULL;
# endif
    struct ifreq   *pCur   = IfConf.ifc_req;
    size_t          cbLeft = IfConf.ifc_len;
    while (cbLeft >= sizeof(*pCur))
    {
# if defined(RT_OS_SOLARIS) || defined(RT_OS_LINUX)
        /* These two do not provide the sa_len member but only support address
         * families which do not need extra bytes on the end. */
#  define SA_LEN(pAddr) sizeof(struct sockaddr)
# elif !defined(SA_LEN)
#  define SA_LEN(pAddr) (pAddr)->sa_len
# endif
        /* Figure the size of the current request. */
        size_t cbCur = RT_UOFFSETOF(struct ifreq, ifr_addr)
                     + SA_LEN(&pCur->ifr_addr);
        cbCur = RT_MAX(cbCur, sizeof(struct ifreq));
# if defined(RT_OS_SOLARIS) || defined(RT_OS_LINUX)
        Assert(pCur->ifr_addr.sa_family == AF_INET);
# endif
        AssertBreak(cbCur <= cbLeft);

# ifdef RT_OS_OS2
        /* On OS/2 we get the MAC address in the AF_LINK that the BSD 4.4 stack
           emits.  We boldly ASSUME these always comes first. */
        if (   pCur->ifr_addr.sa_family == AF_LINK
            && ((struct sockaddr_dl *)&pCur->ifr_addr)->sdl_alen == 6)
            pPrevLinkAddr = pCur;
# endif

        /* Skip it if it's not the kind of address we're looking for. */
        struct ifreq IfReqTmp;
        bool         fIfUp = false;
        bool         fSkip = false;
        if (pCur->ifr_addr.sa_family != AF_INET)
            fSkip = true;
        else
        {
            /* Get the interface flags so we can detect loopback and check if it's up. */
            IfReqTmp = *pCur;
            if (ioctl(sd, SIOCGIFFLAGS, &IfReqTmp) < 0)
            {
                rc = RTErrConvertFromErrno(errno);
                VGSvcError("VMInfo/Network: Failed to ioctl(SIOCGIFFLAGS,%s) on socket: Error %Rrc\n", pCur->ifr_name, rc);
                break;
            }
            fIfUp = !!(IfReqTmp.ifr_flags & IFF_UP);
            if (IfReqTmp.ifr_flags & IFF_LOOPBACK) /* Skip the loopback device. */
                fSkip = true;
        }
        if (!fSkip)
        {
            size_t offSubProp = RTStrPrintf(szPropPath, sizeof(szPropPath), "/VirtualBox/GuestInfo/Net/%RU32", cIfsReported);

            sockaddr_in *pAddress = (sockaddr_in *)&pCur->ifr_addr;
            strcpy(&szPropPath[offSubProp], "/V4/IP");
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, inet_ntoa(pAddress->sin_addr));

            /* Get the broadcast address. */
            IfReqTmp = *pCur;
            if (ioctl(sd, SIOCGIFBRDADDR, &IfReqTmp) < 0)
            {
                rc = RTErrConvertFromErrno(errno);
                VGSvcError("VMInfo/Network: Failed to ioctl(SIOCGIFBRDADDR) on socket: Error %Rrc\n", rc);
                break;
            }
            pAddress = (sockaddr_in *)&IfReqTmp.ifr_broadaddr;
            strcpy(&szPropPath[offSubProp], "/V4/Broadcast");
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, inet_ntoa(pAddress->sin_addr));

            /* Get the net mask. */
            IfReqTmp = *pCur;
            if (ioctl(sd, SIOCGIFNETMASK, &IfReqTmp) < 0)
            {
                rc = RTErrConvertFromErrno(errno);
                VGSvcError("VMInfo/Network: Failed to ioctl(SIOCGIFNETMASK) on socket: Error %Rrc\n", rc);
                break;
            }
# if defined(RT_OS_OS2) || defined(RT_OS_SOLARIS)
            pAddress = (sockaddr_in *)&IfReqTmp.ifr_addr;
# else
            pAddress = (sockaddr_in *)&IfReqTmp.ifr_netmask;
# endif
            strcpy(&szPropPath[offSubProp], "/V4/Netmask");
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, inet_ntoa(pAddress->sin_addr));

# if defined(RT_OS_SOLARIS)
            /*
             * "ifreq" is obsolete on Solaris. We use the recommended "lifreq".
             * We might fail if the interface has not been assigned an IP address.
             * That doesn't matter; as long as it's plumbed we can pick it up.
             * But, if it has not acquired an IP address we cannot obtain it's MAC
             * address this way, so we just use all zeros there.
             */
            RTMAC           IfMac;
            struct lifreq   IfReq;
            RT_ZERO(IfReq);
            AssertCompile(sizeof(IfReq.lifr_name) >= sizeof(pCur->ifr_name));
            strncpy(IfReq.lifr_name, pCur->ifr_name, sizeof(IfReq.lifr_name));
            if (ioctl(sd, SIOCGLIFADDR, &IfReq) >= 0)
            {
                struct arpreq ArpReq;
                RT_ZERO(ArpReq);
                memcpy(&ArpReq.arp_pa, &IfReq.lifr_addr, sizeof(struct sockaddr_in));

                if (ioctl(sd, SIOCGARP, &ArpReq) >= 0)
                    memcpy(&IfMac, ArpReq.arp_ha.sa_data, sizeof(IfMac));
                else
                {
                    rc = RTErrConvertFromErrno(errno);
                    VGSvcError("VMInfo/Network: failed to ioctl(SIOCGARP) on socket: Error %Rrc\n", rc);
                    break;
                }
            }
            else
            {
                VGSvcVerbose(2, "VMInfo/Network: Interface '%s' has no assigned IP address, skipping ...\n", pCur->ifr_name);
                continue;
            }

# elif defined(RT_OS_OS2)
            RTMAC   IfMac;
            if (   pPrevLinkAddr
                && strncmp(pCur->ifr_name, pPrevLinkAddr->ifr_name, sizeof(pCur->ifr_name)) == 0)
            {
                struct sockaddr_dl *pDlAddr = (struct sockaddr_dl *)&pPrevLinkAddr->ifr_addr;
                IfMac = *(PRTMAC)&pDlAddr->sdl_data[pDlAddr->sdl_nlen];
            }
            else
                RT_ZERO(IfMac);

# else
            if (ioctl(sd, SIOCGIFHWADDR, &IfReqTmp) < 0)
            {
                rc = RTErrConvertFromErrno(errno);
                VGSvcError("VMInfo/Network: Failed to ioctl(SIOCGIFHWADDR) on socket: Error %Rrc\n", rc);
                break;
            }
            RTMAC IfMac = *(PRTMAC)&IfReqTmp.ifr_hwaddr.sa_data[0];
# endif

            strcpy(&szPropPath[offSubProp], "/MAC");
            VGSvcPropCacheUpdateF(&g_VMInfoPropCache, szPropPath, "%02X%02X%02X%02X%02X%02X",
                                  IfMac.au8[0], IfMac.au8[1], IfMac.au8[2], IfMac.au8[3], IfMac.au8[4], IfMac.au8[5]);

            strcpy(&szPropPath[offSubProp], "/Status");
            VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, fIfUp ? "Up" : "Down");

            /* The name. */
            strcpy(&szPropPath[offSubProp], "/Name");
            int rc2 = RTStrValidateEncodingEx(pCur->ifr_name, sizeof(pCur->ifr_name), 0);
            if (RT_SUCCESS(rc2))
                VGSvcPropCacheUpdateF(&g_VMInfoPropCache, szPropPath, "%.*s", sizeof(pCur->ifr_name), pCur->ifr_name);
            else
                VGSvcPropCacheUpdate(&g_VMInfoPropCache, szPropPath, NULL);

            cIfsReported++;
        }

        /*
         * Next interface/protocol configuration.
         */
        pCur = (struct ifreq *)((uintptr_t)pCur + cbCur);
        cbLeft -= cbCur;
    }

    RTMemTmpFree(pchBuf);
    close(sd);
    if (RT_FAILURE(rc))
        VGSvcError("VMInfo/Network: Network enumeration for interface %RU32 failed with error %Rrc\n", cIfsReported, rc);

#endif /* !RT_OS_WINDOWS */

#if 1 /* Zapping not enabled yet, needs more testing first. */
    /*
     * Zap all stale network interface data if the former (saved) network ifaces count
     * is bigger than the current one.
     */
    uint32_t cIfsReportedOld; /** @todo r=bird: Cache this internally instead of reading it? */
    rc = VGSvcReadPropUInt32(&g_VMInfoGuestPropSvcClient, g_pszPropCacheValNetCount,
                             &cIfsReportedOld, 0 /*u32Min*/, _1K /*u32Max*/);
    if (RT_SUCCESS(rc))
    {
        if (cIfsReportedOld > cIfsReported)
        {
            VGSvcVerbose(3, "VMInfo/Network: Stale interface data detected (%RU32 old vs. %RU32 current)\n",
                         cIfsReportedOld, cIfsReported);

            uint32_t uIfaceDeleteIdx = cIfsReported;
            for (uint32_t idxDelete = 0; idxDelete < cIfsReportedOld; idxDelete++)
            {
                VGSvcVerbose(3, "VMInfo/Network: Deleting stale data of interface %d ...\n", uIfaceDeleteIdx);
                VGSvcPropCacheUpdateByPath(&g_VMInfoPropCache, NULL, "/VirtualBox/GuestInfo/Net/%RU32", idxDelete);
            }
        }
    }
    else if (rc != VERR_NOT_FOUND)
        VGSvcError("VMInfo/Network: Failed retrieving old network interfaces count with error %Rrc\n", rc);
#endif

    /*
     * This property is a beacon which is _always_ written, even if the network configuration
     * does not change. If this property is missing, the host assumes that all other GuestInfo
     * properties are no longer valid.
     */
    VGSvcPropCacheUpdateF(&g_VMInfoPropCache, g_pszPropCacheValNetCount, "%RU32", cIfsReported);

    /* Don't fail here; just report everything we got. */
    return VINF_SUCCESS;
}


/**
 * @interface_method_impl{VBOXSERVICE,pfnWorker}
 */
static DECLCALLBACK(int) vbsvcVMInfoWorker(bool volatile *pfShutdown)
{
    int rc;

    /*
     * Tell the control thread that it can continue
     * spawning services.
     */
    RTThreadUserSignal(RTThreadSelf());

#ifdef RT_OS_WINDOWS
    /* Required for network information (must be called per thread). */
    if (g_pfnWSAStartup)
    {
        WSADATA wsaData;
        RT_ZERO(wsaData);
        if (g_pfnWSAStartup(MAKEWORD(2, 2), &wsaData))
            VGSvcError("VMInfo/Network: WSAStartup failed! Error: %Rrc\n", RTErrConvertFromWin32(g_pfnWSAGetLastError()));
    }
#endif

    /*
     * Write the fixed properties first.
     */
    vgsvcVMInfoWriteFixedProperties();

    /*
     * Cleanup old properties before we start.
     */
    const char *apszPat[1] = { "/VirtualBox/GuestInfo/Net/*" };
    VbglGuestPropDelSet(&g_VMInfoGuestPropSvcClient, &apszPat[0], RT_ELEMENTS(apszPat));

    /*
     * Now enter the loop retrieving runtime data continuously.
     */
    for (;;)
    {
        rc = vgsvcVMInfoWriteUsers();
        if (RT_FAILURE(rc))
            break;

        rc = vgsvcVMInfoWriteNetwork();
        if (RT_FAILURE(rc))
            break;

        /* Whether to wait for event semaphore or not. */
        bool fWait = true;

        /*
         * Check for location awareness.
         * This most likely only works with VBox 4.1 and later.
         */

        /* Check for new connection. */
        char *pszLAClientID = NULL;
        int rc2 = VGSvcReadHostProp(&g_VMInfoGuestPropSvcClient, g_pszLAActiveClient, true /*fReadOnly*/,
                                    &pszLAClientID, NULL /*ppszFlags*/, NULL /*puTimestamp*/);
        if (RT_SUCCESS(rc2))
        {
            AssertPtr(pszLAClientID);
            if (RTStrICmp(pszLAClientID, "0")) /* Is a client connected? */
            {
                uint32_t uLAClientID = RTStrToInt32(pszLAClientID);
                uint64_t uLAClientAttachedTS;

                /* Peek at "Attach" value to figure out if hotdesking happened. */
                char *pszAttach = NULL;
                rc2 = vgsvcGetLAClientValue(uLAClientID, "Attach", &pszAttach, &uLAClientAttachedTS);

                if (   RT_SUCCESS(rc2)
                    && (   !g_LAClientAttachedTS
                        || (g_LAClientAttachedTS != uLAClientAttachedTS)))
                {
                    vgsvcFreeLAClientInfo(&g_LAClientInfo);

                    /* Note: There is a race between setting the guest properties by the host and getting them by
                     *       the guest. */
                    rc2 = vgsvcGetLAClientInfo(uLAClientID, &g_LAClientInfo);
                    if (RT_SUCCESS(rc2))
                    {
                        VGSvcVerbose(1, "VRDP: Hotdesk client %s with ID=%RU32, Name=%s, Domain=%s\n",
                                     /* If g_LAClientAttachedTS is 0 this means there already was an active
                                      * hotdesk session when VBoxService started. */
                                     !g_LAClientAttachedTS ? "already active" : g_LAClientInfo.fAttached ? "connected" : "disconnected",
                                     uLAClientID, g_LAClientInfo.pszName, g_LAClientInfo.pszDomain);

                        g_LAClientAttachedTS = g_LAClientInfo.uAttachedTS;

                        /* Don't wait for event semaphore below anymore because we now know that the client
                         * changed. This means we need to iterate all VM information again immediately. */
                        fWait = false;
                    }
                    else
                    {
                        static int s_iBitchedAboutLAClientInfo = 0;
                        if (s_iBitchedAboutLAClientInfo < 10)
                        {
                            s_iBitchedAboutLAClientInfo++;
                            VGSvcError("Error getting active location awareness client info, rc=%Rrc\n", rc2);
                        }
                    }
                }
                else if (RT_FAILURE(rc2))
                     VGSvcError("Error getting attached value of location awareness client %RU32, rc=%Rrc\n", uLAClientID, rc2);
                if (pszAttach)
                    RTStrFree(pszAttach);
            }
            else
            {
                VGSvcVerbose(1, "VRDP: UTTSC disconnected from VRDP server\n");
                vgsvcFreeLAClientInfo(&g_LAClientInfo);
            }

            RTStrFree(pszLAClientID);
        }
        else
        {
            static int s_iBitchedAboutLAClient = 0;
            if (   (rc2 != VERR_NOT_FOUND) /* No location awareness installed, skip. */
                && s_iBitchedAboutLAClient < 3)
            {
                s_iBitchedAboutLAClient++;
                VGSvcError("VRDP: Querying connected location awareness client failed with rc=%Rrc\n", rc2);
            }
        }

        VGSvcVerbose(3, "VRDP: Handling location awareness done\n");

        /*
         * Flush all properties if we were restored.
         */
        uint64_t idNewSession = g_idVMInfoSession;
        VbglR3QuerySessionId(&idNewSession);
        if (idNewSession != g_idVMInfoSession)
        {
            VGSvcVerbose(3, "The VM session ID changed, flushing all properties\n");
            vgsvcVMInfoWriteFixedProperties();
            VGSvcPropCacheFlush(&g_VMInfoPropCache);
            g_idVMInfoSession = idNewSession;
        }

        /*
         * Block for a while.
         *
         * The event semaphore takes care of ignoring interruptions and it
         * allows us to implement service wakeup later.
         */
        if (*pfShutdown)
            break;
        if (fWait)
            rc2 = RTSemEventMultiWait(g_hVMInfoEvent, g_cMsVMInfoInterval);
        if (*pfShutdown)
            break;
        if (rc2 == VERR_TIMEOUT)
        { /* likely */ }
        else if (RT_SUCCESS(rc2))
        {
            /* Reset event semaphore if it got triggered. */
            rc2 = RTSemEventMultiReset(g_hVMInfoEvent);
            if (RT_FAILURE(rc2))
                VGSvcError("RTSemEventMultiReset failed; rc2=%Rrc\n", rc2);
        }
        else
        {
            VGSvcError("RTSemEventMultiWait failed; rc2=%Rrc\n", rc2);
            rc = rc2;
            break;
        }
    }

#ifdef RT_OS_WINDOWS
    if (g_pfnWSACleanup)
        g_pfnWSACleanup();
#endif

    return rc;
}


/**
 * @interface_method_impl{VBOXSERVICE,pfnStop}
 */
static DECLCALLBACK(void) vbsvcVMInfoStop(void)
{
    RTSemEventMultiSignal(g_hVMInfoEvent);
}


/**
 * @interface_method_impl{VBOXSERVICE,pfnTerm}
 */
static DECLCALLBACK(void) vbsvcVMInfoTerm(void)
{
    if (g_hVMInfoEvent != NIL_RTSEMEVENTMULTI)
    {
        /* Destroy property cache (will delete or reset temporary values) */
        VGSvcPropCacheTerm(&g_VMInfoPropCache);

        /* Disconnect from guest properties service. */
        VbglGuestPropDisconnect(&g_VMInfoGuestPropSvcClient);

        /* Destroy LA client info. */
        vgsvcFreeLAClientInfo(&g_LAClientInfo);

        RTSemEventMultiDestroy(g_hVMInfoEvent);
        g_hVMInfoEvent = NIL_RTSEMEVENTMULTI;
    }
}


/**
 * The 'vminfo' service description.
 */
VBOXSERVICE g_VMInfo =
{
    /* pszName. */
    "vminfo",
    /* pszDescription. */
    "Virtual Machine Information",
    /* pszUsage. */
    "           [--vminfo-interval <ms>] [--vminfo-user-idle-threshold <ms>]"
    ,
    /* pszOptions. */
    "    --vminfo-interval       Specifies the interval at which to retrieve the\n"
    "                            VM information. The default is 10000 ms.\n"
    "    --vminfo-user-idle-threshold <ms>\n"
    "                            Specifies the user idle threshold (in ms) for\n"
    "                            considering a guest user as being idle. The default\n"
    "                            is 5000 (5 seconds).\n"
    ,
    /* methods */
    vbsvcVMInfoPreInit,
    vbsvcVMInfoOption,
    vbsvcVMInfoInit,
    vbsvcVMInfoWorker,
    vbsvcVMInfoStop,
    vbsvcVMInfoTerm
};

