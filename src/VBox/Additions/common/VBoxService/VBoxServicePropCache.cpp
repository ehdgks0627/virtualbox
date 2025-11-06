/* $Id: VBoxServicePropCache.cpp 111555 2025-11-06 09:49:17Z knut.osmundsen@oracle.com $ */
/** @file
 * VBoxServicePropCache - Guest property cache.
 */

/*
 * Copyright (C) 2010-2025 Oracle and/or its affiliates.
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


/*********************************************************************************************************************************
*   Header Files                                                                                                                 *
*********************************************************************************************************************************/
#include <iprt/assert.h>
#include <iprt/list.h>
#include <iprt/mem.h>
#include <iprt/string.h>

#include <VBox/VBoxGuestLib.h>
#include <VBox/HostServices/GuestPropertySvc.h> /* For GUEST_PROP_MAX_VALUE_LEN */
#include "VBoxServiceInternal.h"
#include "VBoxServiceUtils.h"
#include "VBoxServicePropCache.h"


/**
 * Searches a property within a property cache.
 *
 * @returns A pointer to the found property cache entry on success, or NULL if not found.
 * @param   pCache          The property cache.
 * @param   pszName         Name of property to search for. Case sensitive.
 * @param   fFlags          Search flags. Currently unused and must be 0.
 */
static PVBOXSERVICEVEPROPCACHEENTRY vgsvcPropCacheFindInternal(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName,
                                                               uint32_t fFlags)
{
    RT_NOREF1(fFlags);
    AssertPtrReturn(pCache, NULL);
    AssertPtrReturn(pszName, NULL);

    /** @todo This is a O(n) lookup, maybe improve this later to O(1) using a
     *        map.
     *  r=bird: Use a string space (RTstrSpace*). That is O(log n) in its current
     *        implementation (AVL tree). However, this is not important at the
     *        moment. */
    PVBOXSERVICEVEPROPCACHEENTRY pNode = NULL;
    if (RT_SUCCESS(RTCritSectEnter(&pCache->CritSect)))
    {
        PVBOXSERVICEVEPROPCACHEENTRY pNodeIt;
        RTListForEach(&pCache->NodeHead, pNodeIt, VBOXSERVICEVEPROPCACHEENTRY, NodeSucc)
        {
            if (strcmp(pNodeIt->pszName, pszName) == 0)
            {
                pNode = pNodeIt;
                break;
            }
        }
        RTCritSectLeave(&pCache->CritSect);
    }
    return pNode;
}


/**
 * Inserts (appends) a property into a property cache.
 *
 * @returns A pointer to the inserted property cache entry on success, or NULL on failure.
 * @param   pCache          The property cache.
 * @param   pszName         Name of property to insert. Case sensitive.
 */
static PVBOXSERVICEVEPROPCACHEENTRY vgsvcPropCacheInsertEntryInternal(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName)
{
    AssertPtrReturn(pCache, NULL);
    AssertPtrReturn(pszName, NULL);

    PVBOXSERVICEVEPROPCACHEENTRY pNode = (PVBOXSERVICEVEPROPCACHEENTRY)RTMemAlloc(sizeof(VBOXSERVICEVEPROPCACHEENTRY));
    if (pNode)
    {
        pNode->pszName = RTStrDup(pszName);
        AssertPtrReturnStmt(pNode->pszName, RTMemFree(pNode), NULL);
        pNode->pszValue = NULL;
        pNode->fFlags = 0;
        pNode->pszValueReset = NULL;

        int rc = RTCritSectEnter(&pCache->CritSect);
        if (RT_SUCCESS(rc))
        {
            RTListAppend(&pCache->NodeHead, &pNode->NodeSucc);
            RTCritSectLeave(&pCache->CritSect);

            return pNode;
        }

        RTStrFree(pNode->pszName);
        RTMemFree(pNode);
    }

    return NULL;
}


/**
 * Writes a new value to a property.
 *
 * @returns VBox status code.
 * @param   pClient         The guest property client session info.
 * @param   pszName         Name of property to write value for. Case sensitive.
 * @param   fFlags          Property cache flags of type VGSVCPROPCACHE_FLAGS_XXX.
 * @param   pszValue        The value to write, NULL to delete.
 */
static int vgsvcPropCacheWriteProp(PVBGLGSTPROPCLIENT pClient, const char *pszName, uint32_t fFlags, const char *pszValue)
{
    AssertPtrReturn(pszName, VERR_INVALID_POINTER);

    int rc;
    if (pszValue != NULL)
    {
        if (fFlags & VGSVCPROPCACHE_FLAGS_TRANSIENT)
        {
            /*
             * Because a value can be temporary we have to make sure it also
             * gets deleted when the property cache did not have the chance to
             * gracefully clean it up (due to a hard VM reset etc), so set this
             * guest property using the TRANSRESET flag..
             */
            rc = VbglGuestPropWrite(pClient, pszName, pszValue, "TRANSRESET");
            if (rc == VERR_PARSE_ERROR)
            {
                /* Host does not support the "TRANSRESET" flag, so only
                 * use the "TRANSIENT" flag -- better than nothing :-). */
                rc = VbglGuestPropWrite(pClient, pszName, pszValue, "TRANSIENT");
                /** @todo r=bird: Remember that the host doesn't support this. */
            }
        }
        else
            rc = VbglGuestPropWriteValue(pClient, pszName, pszValue); /* no flags */
    }
    else
        rc = VbglGuestPropWriteValue(pClient, pszName, NULL);
    return rc;
}


#if 0 /* unused */
/**
 * Writes a new value to a property, using a format value.
 *
 * @returns VBox status code.
 * @param   uClientId       The HGCM handle of to the guest property service.
 * @param   pszName         Name of property to write value for. Case sensitive.
 * @param   fFlags          Property cache flags of type VGSVCPROPCACHE_FLAGS_XXX.
 * @param   pszValueFormat  Format string of value to write.
 */
static int vgsvcPropCacheWritePropF(PVBGLGSTPROPCLIENT pClient, const char *pszName, uint32_t fFlags,
                                    const char *pszValueFormat, ...)
{
    int rc;
    if (pszValueFormat != NULL)
    {
        va_list va;
        va_start(va, pszValueFormat);

        char *pszValue;
        if (RTStrAPrintfV(&pszValue, pszValueFormat, va) >= 0)
        {
            rc = vgsvcPropCacheWriteProp(pClient, pszName, fFlags, pszValue);
            RTStrFree(pszValue);
        }
        else
            rc = VERR_NO_MEMORY;
        va_end(va);
    }
    else
        rc = VbglGuestPropWriteValue(pClient, pszName, NULL);
    return rc;
}
#endif


/**
 * Creates a property cache.
 *
 * @returns VBox status code.
 * @param   pCache          Pointer to the cache.
 * @param   uClientId       The HGCM handle of to the guest property service.
 */
int VGSvcPropCacheCreate(PVBOXSERVICEVEPROPCACHE pCache, PVBGLGSTPROPCLIENT pClient)
{
    AssertPtrReturn(pCache, VERR_INVALID_POINTER);
    Assert(pCache->pClient == NULL);

    RTListInit(&pCache->NodeHead);
    int rc = RTCritSectInit(&pCache->CritSect);
    if (RT_SUCCESS(rc))
        pCache->pClient = pClient;
    return rc;
}


/**
 * Updates a cache entry without submitting any changes to the host.
 *
 * This is handy for defining default values/flags.
 *
 * @returns VBox status code.
 * @param   pCache          The property cache.
 * @param   pszName         The property name.
 * @param   fFlags          The property flags to set.
 * @param   pszValueReset   The property reset value.
 */
int VGSvcPropCacheUpdateEntry(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, uint32_t fFlags, const char *pszValueReset)
{
    AssertPtrReturn(pCache, VERR_INVALID_POINTER);
    AssertPtrReturn(pszName, VERR_INVALID_POINTER);
    PVBOXSERVICEVEPROPCACHEENTRY pNode = vgsvcPropCacheFindInternal(pCache, pszName, 0);
    if (pNode == NULL)
        pNode = vgsvcPropCacheInsertEntryInternal(pCache, pszName);

    int rc;
    if (pNode != NULL)
    {
        rc = RTCritSectEnter(&pCache->CritSect);
        if (RT_SUCCESS(rc))
        {
            pNode->fFlags = fFlags;
            if (pszValueReset)
            {
                if (pNode->pszValueReset)
                    RTStrFree(pNode->pszValueReset);
                pNode->pszValueReset = RTStrDup(pszValueReset);
                AssertPtr(pNode->pszValueReset);
            }
            rc = RTCritSectLeave(&pCache->CritSect);
        }
    }
    else
        rc = VERR_NO_MEMORY;
    return rc;
}


/**
 * Updates the local guest property cache and writes it to HGCM if outdated.
 *
 * @returns VBox status code.
 * @retval  VERR_BUFFER_OVERFLOW if the property name or value exceeds the limit.
 * @param   pCache          The property cache.
 * @param   pszName         The property name.
 * @param   pszValueFormat  The property format string.  If this is NULL then
 *                          the property will be deleted (if possible).
 * @param   ...             Format arguments.
 */
int VGSvcPropCacheUpdate(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, const char *pszValueFormat, ...)
{
    AssertPtrReturn(pCache, VERR_INVALID_POINTER);
    AssertPtrReturn(pszName, VERR_INVALID_POINTER);

    AssertPtr(pCache->pClient);

    if (RTStrNLen(pszName, GUEST_PROP_MAX_NAME_LEN) > GUEST_PROP_MAX_NAME_LEN - 1 /* Terminator */)
        return VERR_BUFFER_OVERFLOW;

    /*
     * Format the value first.
     */
    char *pszValue = NULL;
    if (pszValueFormat)
    {
        /** @todo r=bird: Using RTStrAPrintfV is a bit pointless since we have
         *        very low max value length.  The code doesn't even exploit the heap
         *        allocation here, but instead duplicates it ... */
        va_list va;
        va_start(va, pszValueFormat);
        RTStrAPrintfV(&pszValue, pszValueFormat, va);
        va_end(va);
        if (!pszValue)
            return VERR_NO_STR_MEMORY;
        if (RTStrNLen(pszValue, GUEST_PROP_MAX_VALUE_LEN) > GUEST_PROP_MAX_VALUE_LEN - 1 /* Terminator */)
        {
            RTStrFree(pszValue);
            return VERR_BUFFER_OVERFLOW;
        }
    }

    /* Lock the cache. */
    int rc = RTCritSectEnter(&pCache->CritSect);
    if (RT_SUCCESS(rc))
    {
        PVBOXSERVICEVEPROPCACHEENTRY const pNode = vgsvcPropCacheFindInternal(pCache, pszName, 0);
        if (pNode)
        {
            if (pszValue) /* Do we have a value to check for? */
            {
                bool fUpdate = false;
                /* Always update this property, no matter what? */
                if (pNode->fFlags & VGSVCPROPCACHE_FLAGS_ALWAYS_UPDATE)
                    fUpdate = true;
                /* Did the value change so we have to update? */
                else if (pNode->pszValue && strcmp(pNode->pszValue, pszValue) != 0)
                    fUpdate = true;
                /* No value stored at the moment but we have a value now? */
                else if (pNode->pszValue == NULL)
                    fUpdate = true;

                if (fUpdate)
                {
                    /* Write the update. */
                    rc = vgsvcPropCacheWriteProp(pCache->pClient, pNode->pszName, pNode->fFlags, pszValue);
                    VGSvcVerbose(4, "[PropCache %p]: Written '%s'='%s' (flags: %x), rc=%Rrc\n",
                                 pCache, pNode->pszName, pszValue, pNode->fFlags, rc);
                    if (RT_SUCCESS(rc)) /* Only update the node's value on successful write. */
                    {
                        RTStrFree(pNode->pszValue);
                        pNode->pszValue = RTStrDup(pszValue);
                        if (!pNode->pszValue)
                            rc = VERR_NO_MEMORY;
                    }
                }
                else
                    rc = VINF_NO_CHANGE; /* No update needed. */
            }
            else
            {
                /* No value specified. Deletion (or no action required). */
                if (pNode->pszValue) /* Did we have a value before? Then the value needs to be deleted. */
                {
                    rc = vgsvcPropCacheWriteProp(pCache->pClient, pNode->pszName, 0, /*fFlags*/ NULL /*pszValue*/);
                    VGSvcVerbose(4, "[PropCache %p]: Deleted '%s'='%s' (flags: %x), rc=%Rrc\n",
                                 pCache, pNode->pszName, pNode->pszValue, pNode->fFlags, rc);
                    if (RT_SUCCESS(rc)) /* Only delete property value on successful Vbgl deletion. */
                    {
                        /* Delete property (but do not remove from cache) if not deleted yet. */
                        RTStrFree(pNode->pszValue);
                        pNode->pszValue = NULL;
                    }
                }
                else
                    rc = VINF_NO_CHANGE; /* No update needed. */
            }
        }
        else
        {
            AssertMsgFailed(("pszName=%s\n", pszName));
            rc = VERR_NOT_FOUND;
        }

        /* Release cache. */
        RTCritSectLeave(&pCache->CritSect);
    }

    VGSvcVerbose(4, "[PropCache %p]: Updating '%s' resulted in rc=%Rrc\n", pCache, pszName, rc);

    /* Delete temp stuff. */
    RTStrFree(pszValue);
    return rc;
}


/**
 * Updates all cache values which are matching the specified path.
 *
 * @returns VBox status code.
 * @param   pCache          The property cache.
 * @param   pszValue        The value to set.  A NULL will delete the value.
 * @param   fFlags          Flags to set.
 * @param   pszPathFormat   The path format string.  May not be null and has
 *                          to be an absolute path.
 * @param   ...             Format arguments.
 */
int VGSvcPropCacheUpdateByPath(PVBOXSERVICEVEPROPCACHE pCache, const char *pszValue, uint32_t fFlags,
                               const char *pszPathFormat, ...)
{
    RT_NOREF1(fFlags);
    AssertPtrReturn(pCache, VERR_INVALID_POINTER);
    AssertPtrReturn(pszPathFormat, VERR_INVALID_POINTER);

    int rc = VERR_NOT_FOUND;
    if (RT_SUCCESS(RTCritSectEnter(&pCache->CritSect)))
    {
        /*
         * Format the value first.
         */
        /** @todo r=bird: The max path length is 64 bytes, including terminator.
         *        Why involve any heap here? */
        char *pszPath = NULL;
        va_list va;
        va_start(va, pszPathFormat);
        RTStrAPrintfV(&pszPath, pszPathFormat, va);
        va_end(va);
        if (!pszPath)
        {
            rc = VERR_NO_STR_MEMORY;
        }
        else
        {
            /* Iterate through all nodes and compare their paths. */
            PVBOXSERVICEVEPROPCACHEENTRY pNodeIt;
            RTListForEach(&pCache->NodeHead, pNodeIt, VBOXSERVICEVEPROPCACHEENTRY, NodeSucc)
            {
                /** @todo r=bird: This is a _very_ inefficient way of writing RTStrStartsWith(pNodeIt->pszName, pszPath).
                 * Better:
                 * size_t const cchPath = strlen(pszPath);
                 * ...
                 *     if (RTStrNCmp(pNodeIt->pszName, pszPath, cchPath) == 0) */
                if (RTStrStr(pNodeIt->pszName, pszPath) == pNodeIt->pszName)
                {
                    /** @todo Use some internal function to update the node directly, this is slow atm. */
                    rc = VGSvcPropCacheUpdate(pCache, pNodeIt->pszName, pszValue);
                }
                if (RT_FAILURE(rc))
                    break;
            }
            RTStrFree(pszPath);
        }
        RTCritSectLeave(&pCache->CritSect);
    }
    return rc;
}


/**
 * Flushes the cache by writing every item regardless of its state.
 *
 * @returns VBox status code.
 * @param   pCache          The property cache.
 */
int VGSvcPropCacheFlush(PVBOXSERVICEVEPROPCACHE pCache)
{
    AssertPtrReturn(pCache, VERR_INVALID_POINTER);

    int rc = VINF_SUCCESS;
    if (RT_SUCCESS(RTCritSectEnter(&pCache->CritSect)))
    {
        PVBOXSERVICEVEPROPCACHEENTRY pNodeIt;
        RTListForEach(&pCache->NodeHead, pNodeIt, VBOXSERVICEVEPROPCACHEENTRY, NodeSucc)
        {
            rc = vgsvcPropCacheWriteProp(pCache->pClient, pNodeIt->pszName, pNodeIt->fFlags, pNodeIt->pszValue);
            if (RT_FAILURE(rc))
                break;
        }
        RTCritSectLeave(&pCache->CritSect);
    }
    return rc;
}


/**
 * Reset all temporary properties and destroy the cache.
 *
 * @param   pCache          The property cache.
 */
void VGSvcPropCacheDestroy(PVBOXSERVICEVEPROPCACHE pCache)
{
    AssertPtrReturnVoid(pCache);
    AssertReturnVoid(pCache->pClient);

    /* Lock the cache. */
    int rc = RTCritSectEnter(&pCache->CritSect);
    if (RT_SUCCESS(rc))
    {
        /** @todo r=bird: Use RTListForEachSafe! */
        PVBOXSERVICEVEPROPCACHEENTRY pNode = RTListGetFirst(&pCache->NodeHead, VBOXSERVICEVEPROPCACHEENTRY, NodeSucc);
        while (pNode)
        {
            PVBOXSERVICEVEPROPCACHEENTRY pNext = RTListNodeIsLast(&pCache->NodeHead, &pNode->NodeSucc)
                                                                  ? NULL
                                                                  : RTListNodeGetNext(&pNode->NodeSucc,
                                                                                      VBOXSERVICEVEPROPCACHEENTRY, NodeSucc);
            RTListNodeRemove(&pNode->NodeSucc);

            if (pNode->fFlags & VGSVCPROPCACHE_FLAGS_TEMPORARY)
                vgsvcPropCacheWriteProp(pCache->pClient, pNode->pszName, pNode->fFlags, pNode->pszValueReset);

            AssertPtr(pNode->pszName);
            RTStrFree(pNode->pszName);
            RTStrFree(pNode->pszValue);
            RTStrFree(pNode->pszValueReset);
            pNode->fFlags = 0;

            RTMemFree(pNode);

            pNode = pNext;
        }
        RTCritSectLeave(&pCache->CritSect);
    }

    /* Destroy critical section. */
    RTCritSectDelete(&pCache->CritSect);
    pCache->pClient = NULL;
}

