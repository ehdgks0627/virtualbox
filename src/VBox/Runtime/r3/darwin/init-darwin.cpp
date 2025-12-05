/* $Id: init-darwin.cpp 112040 2025-12-05 11:29:33Z alexander.eichner@oracle.com $ */
/** @file
 * IPRT - Init Ring-3, POSIX Specific Code.
 */

/*
 * Copyright (C) 2025 Oracle and/or its affiliates.
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
 * The contents of this file may alternatively be used under the terms
 * of the Common Development and Distribution License Version 1.0
 * (CDDL), a copy of it is provided in the "COPYING.CDDL" file included
 * in the VirtualBox distribution, in which case the provisions of the
 * CDDL are applicable instead of those of the GPL.
 *
 * You may elect to license modified versions of this file under the
 * terms and conditions of either the GPL or the CDDL or both.
 *
 * SPDX-License-Identifier: GPL-3.0-only OR CDDL-1.0
 */


/*********************************************************************************************************************************
*   Header Files                                                                                                                 *
*********************************************************************************************************************************/
#define LOG_GROUP RTLOGGROUP_DEFAULT
#include <iprt/initterm.h>
#include <iprt/assert.h>
#include <iprt/errcore.h>
#include <iprt/log.h>
#include <iprt/param.h>
#include <iprt/string.h>
#include <iprt/system.h>
#include <iprt/thread.h>
#include "../init.h"

#include "internal/thread.h"

#include <signal.h>
#define _XOPEN_SOURCE
#include <ucontext.h>
#include <mach/mach.h>
#include <mach-o/dyld.h>


/*********************************************************************************************************************************
*   Structures and Typedefs                                                                                                      *
*********************************************************************************************************************************/


/*********************************************************************************************************************************
*   Global Variables                                                                                                             *
*********************************************************************************************************************************/
static struct sigaction g_SigActionSegv;  /**< The default action for SIGSEGV. */
static struct sigaction g_SigActionBus;   /**< The default action for SIGBUS. */
static struct sigaction g_SigActionAbort; /**< The default action for SIGABRT. */


/*********************************************************************************************************************************
*   Internal Functions                                                                                                           *
*********************************************************************************************************************************/

/**
 * Signal handler callback.
 *
 * Will try log stuff.
 */
static void rtR3DarwinSigSegvBusHandler(int iSignum, siginfo_t *pSigInfo, void *pvContext)
{
    /* Restore the default handler so we do the default action after we finished. */
    struct sigaction *pAction = NULL;
    if (iSignum == SIGSEGV)
        pAction = &g_SigActionSegv;
    else if (iSignum == SIGBUS)
        pAction = &g_SigActionBus;
    else
        pAction = &g_SigActionAbort;
    sigaction(iSignum, pAction, NULL);

    /*
     * Try get the logger and log exception details.
     *
     * Note! We'll be using RTLogLoggerWeak for now, though we should probably add
     *       a less deadlock prone API here and gives up pretty fast if it
     *       cannot get the lock...
     */
    PRTLOGGER pLogger = RTLogRelGetDefaultInstanceWeak();
    if (!pLogger)
        pLogger = RTLogGetDefaultInstanceWeak();
    if (pLogger)
    {
        RTLogLoggerWeak(pLogger, NULL, "\n!!! rtR3DarwinSigSegvBusHandler caught an exception on thread %p in %u !!!\n",
                        RTThreadNativeSelf(), RTProcSelf());

        /*
         * Dump the signal info.
         */
        RTLogLoggerWeak(pLogger, NULL,  "\nsi_signo=%RI32 si_code=%RI32 si_pid=%RI32\n"
                                        "si_uid=%RI32 si_addr=%p si_status=%RI32\n",
                        pSigInfo->si_signo, pSigInfo->si_code, pSigInfo->si_pid,
                        pSigInfo->si_uid, pSigInfo->si_addr, pSigInfo->si_status);

        /* Dump stack information. */
        ucontext_t *pCtx = (ucontext_t *)pvContext;
        RTLogLoggerWeak(pLogger, NULL,  "\nuc_stack.ss_sp=%p uc_stack.ss_flags=%RX32 uc_stack.ss_size=%zu\n",
                        pCtx->uc_stack.ss_sp, pCtx->uc_stack.ss_flags, pCtx->uc_stack.ss_size);

        /*
         * Dump the machine context.
         */
        uintptr_t     uXcptPC = 0;
        uintptr_t     uXcptSP = 0;
        mcontext_t    pXcptCtx = pCtx->uc_mcontext;
#ifdef RT_ARCH_AMD64
        RTLogLoggerWeak(pLogger, NULL, "\ncs:rip=%04x:%016RX64\n",
                        pXcptCtx->__ss.__cs, pXcptCtx->__ss.__rip);
        RTLogLoggerWeak(pLogger, NULL, "rsp=%016RX64 rbp=%016RX64\n",
                        pXcptCtx->__ss.__rsp, pXcptCtx->__ss.__rbp);
        RTLogLoggerWeak(pLogger, NULL, "rax=%016RX64 rcx=%016RX64 rdx=%016RX64 rbx=%016RX64\n",
                        pXcptCtx->__ss.__rax, pXcptCtx->__ss.__rcx, pXcptCtx->__ss.__rdx, pXcptCtx->__ss.__rbx);
        RTLogLoggerWeak(pLogger, NULL, "rsi=%016RX64 rdi=%016RX64 rsp=%016RX64 rbp=%016RX64\n",
                        pXcptCtx->__ss.__rsi, pXcptCtx->__ss.__rdi, pXcptCtx->__ss.__rsp, pXcptCtx->__ss.__rbp);
        RTLogLoggerWeak(pLogger, NULL, "r8 =%016RX64 r9 =%016RX64 r10=%016RX64 r11=%016RX64\n",
                        pXcptCtx->__ss.__r8,  pXcptCtx->__ss.__r9,  pXcptCtx->__ss.__r10, pXcptCtx->__ss.__r11);
        RTLogLoggerWeak(pLogger, NULL, "r12=%016RX64 r13=%016RX64 r14=%016RX64 r15=%016RX64\n",
                        pXcptCtx->__ss.__r12,  pXcptCtx->__ss.__r13,  pXcptCtx->__ss.__r14, pXcptCtx->__ss.__r15);
        RTLogLoggerWeak(pLogger, NULL, "fs=%04x gs=%04x eflags=%08x\n",
                        pXcptCtx->__ss.__fs, pXcptCtx->__ss.__gs,
                        pXcptCtx->__ss.__rflags);
        uXcptSP = pXcptCtx->__ss.__rsp;
        uXcptPC = pXcptCtx->__ss.__rip;

#elif defined(RT_ARCH_X86)
        /** @todo Only useful for the guest additions which aren't officially supported, so not worth the hassle right now. */
#elif defined(RT_ARCH_ARM64)
        uXcptSP = arm_thread_state64_get_sp(pXcptCtx->__ss);
        uXcptPC = arm_thread_state64_get_pc(pXcptCtx->__ss);

        RTLogLoggerWeak(pLogger, NULL, "\npc=%016RX64 pstate=%08RX32\n", uXcptPC, pXcptCtx->__ss.__cpsr);
        RTLogLoggerWeak(pLogger, NULL, "sp=%016RX64\n", uXcptSP);
        RTLogLoggerWeak(pLogger, NULL, "r0=%016RX64 r1=%016RX64 r2=%016RX64 r3=%016RX64\n",
                        pXcptCtx->__ss.__x[0], pXcptCtx->__ss.__x[1], pXcptCtx->__ss.__x[2], pXcptCtx->__ss.__x[3]);
        RTLogLoggerWeak(pLogger, NULL, "r4=%016RX64 r5=%016RX64 r6=%016RX64 r7=%016RX64\n",
                        pXcptCtx->__ss.__x[4], pXcptCtx->__ss.__x[5], pXcptCtx->__ss.__x[6], pXcptCtx->__ss.__x[7]);
        RTLogLoggerWeak(pLogger, NULL, "r8=%016RX64 r9=%016RX64 r10=%016RX64 r11=%016RX64\n",
                        pXcptCtx->__ss.__x[8], pXcptCtx->__ss.__x[9], pXcptCtx->__ss.__x[10], pXcptCtx->__ss.__x[11]);
        RTLogLoggerWeak(pLogger, NULL, "r12=%016RX64 r13=%016RX64 r14=%016RX64 r15=%016RX64\n",
                        pXcptCtx->__ss.__x[12], pXcptCtx->__ss.__x[13], pXcptCtx->__ss.__x[14], pXcptCtx->__ss.__x[15]);
        RTLogLoggerWeak(pLogger, NULL, "r16=%016RX64 r17=%016RX64 r18=%016RX64 r19=%016RX64\n",
                        pXcptCtx->__ss.__x[16], pXcptCtx->__ss.__x[17], pXcptCtx->__ss.__x[18], pXcptCtx->__ss.__x[19]);
        RTLogLoggerWeak(pLogger, NULL, "r20=%016RX64 r21=%016RX64 r22=%016RX64 r23=%016RX64\n",
                        pXcptCtx->__ss.__x[20], pXcptCtx->__ss.__x[21], pXcptCtx->__ss.__x[22], pXcptCtx->__ss.__x[23]);
        RTLogLoggerWeak(pLogger, NULL, "r24=%016RX64 r25=%016RX64 r26=%016RX64 r27=%016RX64\n",
                        pXcptCtx->__ss.__x[24], pXcptCtx->__ss.__x[25], pXcptCtx->__ss.__x[26], pXcptCtx->__ss.__x[27]);
        RTLogLoggerWeak(pLogger, NULL, "r28=%016RX64 r29=%016RX64 r30=%016RX64\n",
                        pXcptCtx->__ss.__x[28], arm_thread_state64_get_fp(pXcptCtx->__ss), arm_thread_state64_get_lr(pXcptCtx->__ss));
#endif

        /*
         * Dump stack.
         */
        uintptr_t uStack = uXcptSP;
        uStack -= uStack & 15;

        /* Dump at least a page. */
        uint32_t const cbPage = RTSystemGetPageSize();
        size_t cbToDump = cbPage - (uStack & RTSystemGetPageOffsetMask());
        uintptr_t uTop = 0;

        /* Try to figure out the stack top, this doesn't work for adopted or the main thread. */
        RTTHREAD hSelf = RTThreadSelf();
        if (hSelf != NIL_RTTHREAD)
        {
            PRTTHREADINT pThread = rtThreadGet(hSelf);
            if (pThread)
            {
                if (!(pThread->fIntFlags & (RTTHREADINT_FLAGS_ALIEN | RTTHREADINT_FLAGS_MAIN)))
                {
                    uTop = (uintptr_t)rtThreadGetStackTop(pThread);
                    cbToDump = uTop - uStack;
                }
                rtThreadRelease(pThread);
            }
        }

        RTLogLoggerWeak(pLogger, NULL, "\nStack %p, dumping %#zx bytes (top %p)\n", uStack, cbToDump, uTop);
        RTLogLoggerWeak(pLogger, NULL, "%.*RhxD\n", cbToDump, uStack);

        /*
         * Try figure the thread name.
         *
         * Note! This involves the thread db lock, so it may deadlock, which
         *       is why it's at the end.
         */
        RTLogLoggerWeak(pLogger, NULL,  "Thread ID:   %p\n", RTThreadNativeSelf());
        RTLogLoggerWeak(pLogger, NULL,  "Thread name: %s\n", RTThreadSelfName());
        RTLogLoggerWeak(pLogger, NULL,  "Thread IPRT: %p\n", hSelf);

        /*
         * Try dump the load information.
         */
        RTLogLoggerWeak(pLogger, NULL,
                        "\nLoaded Modules:\n"
                        "%-*s[*] Path\n", sizeof(void *) * 4 + 2 - 1, "Address range"
                        );

        /** @todo This is not working right. */
        uint32_t const cImages = _dyld_image_count();
        for (uint32_t i = 0; i < cImages; i++)
        {
            RTLogLoggerWeak(pLogger, NULL, "%p..%p%c  %s\n",
                            _dyld_get_image_vmaddr_slide(i), 0, ' ', _dyld_get_image_name(i));
        }

        /*
         * Dump the command line.
         */
    }
}


static int rtR3InitNativeObtrusiveWorker(uint32_t fFlags)
{
    RT_NOREF(fFlags);

    /* Install our own SIGSEGV/SIGBUS/SIGABORT handlers. */
    struct sigaction Action; RT_ZERO(Action);
    Action.sa_flags     = SA_SIGINFO;
    Action.sa_sigaction = rtR3DarwinSigSegvBusHandler;
    sigaction(SIGSEGV, &Action, &g_SigActionSegv);
    sigaction(SIGBUS,  &Action, &g_SigActionBus);
    sigaction(SIGBUS,  &Action, &g_SigActionAbort);
    /* Ignore errors. */

    return VINF_SUCCESS;
}


DECLHIDDEN(int)  rtR3InitNativeFirst(uint32_t fFlags)
{
    int rc = VINF_SUCCESS;
    if (!(fFlags & RTR3INIT_FLAGS_UNOBTRUSIVE))
        rc = rtR3InitNativeObtrusiveWorker(fFlags);

    return rc;
}


DECLHIDDEN(void) rtR3InitNativeObtrusive(uint32_t fFlags)
{
    rtR3InitNativeObtrusiveWorker(fFlags);
}


DECLHIDDEN(int)  rtR3InitNativeFinal(uint32_t fFlags)
{
    /* Nothing to do here. */
    RT_NOREF_PV(fFlags);
    return VINF_SUCCESS;
}

