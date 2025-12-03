' $Id: configure.py.vbs 111995 2025-12-03 14:57:58Z andreas.loeffler@oracle.com $
' Thin VBScript wrapper to call configure.py with passed arguments.

'
' Copyright (C) 2025 Oracle and/or its affiliates.
'
' This file is part of VirtualBox base platform packages, as
' available from https://www.virtualbox.org.
'
' This program is free software; you can redistribute it and/or
' modify it under the terms of the GNU General Public License
' as published by the Free Software Foundation, in version 3 of the
' License.
'
' This program is distributed in the hope that it will be useful, but
' WITHOUT ANY WARRANTY; without even the implied warranty of
' MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
' General Public License for more details.
'
' You should have received a copy of the GNU General Public License
' along with this program; if not, see <https://www.gnu.org/licenses>.
'
' SPDX-License-Identifier: GPL-3.0-only
'

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Combine passed arguments.
strArgs = ""
For i = 1 To WScript.Arguments.Count
    strArgs = strArgs & " " & Chr(34) & WScript.Arguments(i-1) & Chr(34)
Next

' Try python3, then just python.
strPythonPath = ""
If Not objShell.Exec("cmd /c where python3").StdOut.AtEndOfStream Then
    strPythonPath = "python3"
ElseIf Not objShell.Exec("cmd /c where python").StdOut.AtEndOfStream Then
    strPythonPath = "python"
End If

WScript.Echo "Deprecation notice: VBScript has been marked as being deprecated and will be removed in the future."
WScript.Echo "                    Please either invoke configure.py via Python or use the Powershell script via configure.ps1"
WScript.Echo ""
WScript.Sleep 3000 ' Make it painful to use.

If strPythonPath = "" Then
    WScript.Echo "Python is not found."
    WScript.Echo ""
    WScript.Echo "Python 3 is required in order to build VirtualBox."
    WScript.Echo "Please install Python 3 and ensure it is in your PATH."
    WScript.Quit 1
End If

' Execute configure.py with arguments.
strCmd = "cmd /c " & strPythonPath & " configure.py" & strArgs & " 2>&1"
Set oProc = objShell.Exec(strCmd)
Do While Not oProc.StdOut.AtEndOfStream
    WScript.StdOut.WriteLine oProc.StdOut.ReadLine
Loop

' Pass back exit code from configure.py.
WScript.Quit oProc.ExitCode
