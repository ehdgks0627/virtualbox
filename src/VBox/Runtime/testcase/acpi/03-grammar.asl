/* $Id: 03-grammar.asl 112621 2026-01-16 09:46:12Z alexander.eichner@oracle.com $ */
/** @file
 * VirtualBox ACPI - TPM ACPI device.
 */

/*
 * Copyright (C) 2021-2024 Oracle and/or its affiliates.
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

DefinitionBlock ("", "SSDT", 1, "VBOX  ", "VBOXTPMT", 2)
{
    Scope (_SB_)
    {
        Device (DUT_)
        {
            Method (TEST, 7, NotSerialized, 0)
            {
                If (LEqual(IFID, One))
                {
                    Return ("PNP0C31")
                }
                Else
                {
                    Return ("MSFT0101")
                }

                And(Arg0, Arg1, Arg2)
                Or(Arg0, Arg1, Arg2)
                Xor(Arg0, Arg1, Arg2)
                Nand(Local0, Local1, Local2)
                ShiftLeft(Arg0, Arg1, Arg2)
                ShiftRight(Arg0, Arg1, Arg2)

                Index(Local0, Local1, Local2)
                Add(Local0, Local1, Local2)
                Subtract(Local0, Local1, Local2)
                Multiply(Local7, Arg6, Arg5)

                Store(Local0, Local7)
                Increment(Local7)
                Decrement(Local6)
            }
        }
    }
}

/*
 * Local Variables:
 * comment-start: "//"
 * End:
 */

