/* $Id: */
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

#ifndef GA_INCLUDED_SRC_common_VBoxService_VBoxServicePropCache_h
#define GA_INCLUDED_SRC_common_VBoxService_VBoxServicePropCache_h
#ifndef RT_WITHOUT_PRAGMA_ONCE
# pragma once
#endif

#include "VBoxServiceInternal.h"

#ifdef VBOX_WITH_GUEST_PROPS

/** @name VGSVCPROPCACHE_FLAG_XXX - Guest Property Cache Flags.
 * @{ */
/** Indicates wheter a guest property is temporary and either should
 *  - a) get a "reset" value assigned (via VBoxServicePropCacheUpdateEntry)
 *       as soon as the property cache gets destroyed, or
 *  - b) get deleted when no reset value is specified.
 */
# define VGSVCPROPCACHE_FLAGS_TEMPORARY             RT_BIT_32(0)
/** Indicates whether a property every time needs to be updated, regardless
 *  if its real value changed or not. */
# define VGSVCPROPCACHE_FLAGS_ALWAYS_UPDATE         RT_BIT_32(1)
/** The guest property gets deleted when the VM gets shutdown, rebooted, reset,
 *  or powered off.  Maps directly to the guest property TRANSRESET flag. */
# define VGSVCPROPCACHE_FLAGS_TRANSIENT             RT_BIT_32(2)

/** Same as VGSVCPROPCACHE_FLAGS_TEMPORARY|VGSVCPROPCACHE_FLAGS_TEMPORARY to
 *  convey intention at reset. */
# define VGSVCPROPCACHE_FLAGS_TMP_DEL_TRANSRESET    (VGSVCPROPCACHE_FLAGS_TEMPORARY | VGSVCPROPCACHE_FLAGS_TRANSIENT)
/** @}  */

int  VGSvcPropCacheInit(PVBOXSERVICEVEPROPCACHE pCache, PVBGLGSTPROPCLIENT pClient);
void VGSvcPropCacheTerm(PVBOXSERVICEVEPROPCACHE pCache);
int  VGSvcPropCacheDeclareEntry(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, uint32_t fFlags,
                                const char *pszValueReset = NULL);
int  VGSvcPropCacheUpdate(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, const char *pszValue);
int  VGSvcPropCacheUpdateF(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, const char *pszValueFormat, ...) RT_IPRT_FORMAT_ATTR(3, 4);
int  VGSvcPropCacheUpdateEx(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, const char *pszValue,
                            uint32_t fFlags, const char *pszValueReset);
int  VGSvcPropCacheUpdateExF(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, uint32_t fFlags, const char *pszValueReset,
                             const char *pszValueFormat, ...) RT_IPRT_FORMAT_ATTR(5, 6);
int  VGSvcPropCacheUpdateTdtr(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, const char *pszValue);
int  VGSvcPropCacheUpdateTdtrF(PVBOXSERVICEVEPROPCACHE pCache, const char *pszName, const char *pszValueFormat, ...) RT_IPRT_FORMAT_ATTR(3, 4);
int  VGSvcPropCacheUpdateByPath(PVBOXSERVICEVEPROPCACHE pCache, const char *pszValue, const char *pszPathFormat, ...);
int  VGSvcPropCacheMarkNotUpdatedByPath(PVBOXSERVICEVEPROPCACHE pCache, const char *pszPath);
int  VGSvcPropCachedDeleteNotUpdated(PVBOXSERVICEVEPROPCACHE pCache);
int  VGSvcPropCacheFlush(PVBOXSERVICEVEPROPCACHE pCache);
#endif /* VBOX_WITH_GUEST_PROPS */

#endif /* !GA_INCLUDED_SRC_common_VBoxService_VBoxServicePropCache_h */

