#!/usr/bin/env python3
"""
Configuration script for building VirtualBox.
"""

# -*- coding: utf-8 -*-
# $Id: configure.py 112048 2025-12-05 14:44:35Z andreas.loeffler@oracle.com $
# pylint: disable=consider-using-f-string
# pylint: disable=global-statement
# pylint: disable=line-too-long
# pylint: disable=too-many-lines
# pylint: disable=unnecessary-semicolon
# pylint: disable=import-error
# pylint: disable=import-outside-toplevel
# pylint: disable=invalid-name
__copyright__ = \
"""
Copyright (C) 2025 Oracle and/or its affiliates.

This file is part of VirtualBox base platform packages, as
available from https://www.virtualbox.org.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation, in version 3 of the
License.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, see <https://www.gnu.org/licenses>.

SPDX-License-Identifier: GPL-3.0-only
"""

import argparse
import ctypes
import datetime
import fnmatch
import glob
import importlib;
import io
import os
import platform
import re
import shlex
import shutil
import subprocess
import sysconfig # Since Python 3.2.
import sys
import tempfile

g_sScriptPath = os.path.abspath(os.path.dirname(__file__));
g_sScriptName = os.path.basename(__file__);
g_sOutPath    = os.path.join(g_sScriptPath, 'out');
g_sDevPath    = os.path.join(g_sScriptPath, 'tools');
g_sDevBinPath = None; # Determined at runtime.

class Log(io.TextIOBase):
    """
    Duplicates output to multiple file-like objects (used for logging and stdout).
    """
    def __init__(self, *files):
        self.asFiles = files;
    def write(self, data):
        """
        Write data to all files.
        """
        for f in self.asFiles:
            f.write(data);
    def flush(self):
        """
        Flushes all files.
        """
        for f in self.asFiles:
            if not f.closed:
                f.flush();

class BuildArch:
    """
    Supported build architectures enumeration.
    This resembles the kBuild architectures.
    """
    UNKNOWN = "unknown";
    X86 = "x86";
    AMD64 = "amd64";
    ARM64 = "arm64";

# Defines the host architecture.
g_sHostArch = platform.machine().lower();
# Map host arch to build arch.
g_enmHostArch = {
    "i386": BuildArch.X86,
    "i686": BuildArch.X86,
    "x86_64": BuildArch.AMD64,
    "amd64": BuildArch.AMD64,
    "aarch64": BuildArch.ARM64,
    "arm64": BuildArch.ARM64
}.get(g_sHostArch, BuildArch.UNKNOWN);

class BuildTarget:
    """
    Supported build targets enumeration.
    This resembles the kBuild targets.
    """
    ANY = "any";
    LINUX = "linux";
    WINDOWS = "win";
    DARWIN = "darwin";
    SOLARIS = "solaris";
    BSD = "bsd";
    HAIKU = "haiku";
    UNKNOWN = "unknown";

g_fDebug = False;             # Enables debug mode. Only for development.
g_fContOnErr = False;           # Continue on fatal errors.
g_sEnvVarPrefix = 'VBOX_';
g_sFileLog = 'configure.log'; # Log file path.
g_cVerbosity = 0;
g_cErrors = 0;
g_cWarnings = 0;

# Defines the host target.
g_sHostTarget = platform.system().lower();
# Maps Python system string to kBuild build targets.
g_enmHostTarget = {
    "linux":    BuildTarget.LINUX,
    "windows":  BuildTarget.WINDOWS,
    "darwin":   BuildTarget.DARWIN,
    "solaris":  BuildTarget.SOLARIS,
    "freebsd":  BuildTarget.BSD,
    "openbsd":  BuildTarget.BSD,
    "netbsd":   BuildTarget.BSD,
    "haiku":    BuildTarget.HAIKU,
    "":         BuildTarget.UNKNOWN
}.get(g_sHostTarget, BuildTarget.UNKNOWN);

class BuildType:
    """
    Supported build types enumeration.
    This resembles the kBuild targets.
    """
    DEBUG = "debug";
    RELEASE = "release";
    PROFILE = "profile";

# Dictionary of path lists to prepend to something.
# See command line arguments '--prepend-<something>-path'.
# Note: The keys must match <something>, e.g. 'programfiles' (for parsing).
g_asPathsPrepend = { 'programfiles' : [], 'ewdk'  : [], 'tools'  : [] };
# Dictionary of path lists to append to something.
# See command line arguments '--append-<something>-path'.
# Note: The keys must match <something>, e.g. 'programfiles' (for parsing).
g_asPathsAppend = { 'programfiles' : [], 'ewdk'  : [], 'tools'  : [] };


def printWarn(sMessage, fLogOnly = False, fDontCount = False):
    """
    Prints warning message to stdout.
    """
    _ = fLogOnly;
    print(f"--> Warning: {sMessage}", file=sys.stdout);
    if not fDontCount:
        globals()['g_cWarnings'] += 1;

def printError(sMessage, fLogOnly = False, fDontCount = False):
    """
    Prints an error message to stderr.
    """
    _ = fLogOnly;
    print(f"*** Error: {sMessage}", file=sys.stderr);
    if not fDontCount:
        globals()['g_cErrors'] += 1;

def printVerbose(uVerbosity, sMessage, fLogOnly = False):
    """
    Prints a verbose message if the global verbosity level is high enough.
    """
    _ = fLogOnly;
    if g_cVerbosity >= uVerbosity:
        print(f"--- {sMessage}");

def getLinuxGnuTypeFromPlatform():
    """
    Returns the Linux GNU type based on the platform.
    """
    mapPlatform2GnuType = {
        "x86_64": "x86_64-linux-gnu",
        "amd64": "x86_64-linux-gnu",
        "i386": "i386-linux-gnu",
        "i686": "i386-linux-gnu",
        "aarch64": "aarch64-linux-gnu",
        "arm64": "aarch64-linux-gnu",
        "armv7l": "arm-linux-gnueabihf",
        "armv6l": "arm-linux-gnueabi",
        "ppc64le": "powerpc64le-linux-gnu",
        "s390x": "s390x-linux-gnu",
        "riscv64": "riscv64-linux-gnu",
    };
    return mapPlatform2GnuType.get(platform.machine().lower());

def checkWhich(sCmdName, sToolDesc = None, sCustomPath = None, asVersionSwitches = None):
    """
    Helper to check for a command in PATH or custom path.

    Returns a tuple of (command path, version string) or (None, None) if not found.
    """

    sExeSuff = ".exe" if g_enmHostTarget == BuildTarget.WINDOWS else "";
    if not sCmdName.endswith(sExeSuff):
        sCmdName += sExeSuff;

    sCmdPath = None;
    if sCustomPath:
        sCmdPath = os.path.join(sCustomPath, sCmdName);
        if os.path.isfile(sCmdPath) and os.access(sCmdPath, os.X_OK):
            printVerbose(1, f"Found '{sCmdName}' at custom path: {sCmdPath}");
        else:
            printError(f"'{sCmdName}' not found at custom path: {sCmdPath}");
            return None, None;
    else:
        sCmdPath = shutil.which(sCmdName);
        if sCmdPath:
            printVerbose(1, f"Found '{sCmdName}' at: {sCmdPath}");

    # Try to get version.
    if sCmdPath:
        if not asVersionSwitches:
            asVersionSwitches = [ '--version', '-V', '/?', '/h', '/help', '-version', 'version' ];
        try:
            for sSwitch in asVersionSwitches:
                oProc = subprocess.run([sCmdPath, sSwitch], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10);
                if oProc.returncode == 0:
                    sVer = oProc.stdout.decode('utf-8', 'replace').strip().splitlines()[0];
                    printVerbose(1, f"Detected version for '{sCmdName}' is: {sVer}");
                    return sCmdPath, sVer;
            return sCmdPath, '<unknown>';
        except subprocess.SubprocessError as ex:
            printError(f"Error while checking version of {sToolDesc if sToolDesc else sCmdName}: {str(ex)}");
        return None, None;

    printError(f"'{sCmdName}' not found in PATH.");
    return None, None;

def getLinkerArgs(enmBuildTarget, asLibFiles):
    """
    Returns the linker arguments for the library as a list.

    Returns an empty list for no libs.
    """
    if not asLibFiles:
        return [];

    asLibArgs = [];

    if enmBuildTarget == BuildTarget.WINDOWS:
        asLibArgs.extend( [ '/link' ]);

    for sLibCur in asLibFiles:
        if enmBuildTarget == BuildTarget.WINDOWS:
            asLibArgs.extend( [ sLibCur + '.lib'] );
        else:
            # Remove 'lib' prefix if present for -l on UNIX-y OSes.
            if sLibCur.startswith("lib"):
                sLibCur = sLibCur[3:];
            else:
                sLibCur = ':' + sLibCur;
            asLibArgs += [ f'-l{sLibCur}' ];
    return asLibArgs;

def hasCPPHeader(asHeader):
    """
    Rough guess which headers require C++.

    Returns True if it requires C++, False if C only.
    """
    if len(asHeader) == 0:
        return False; # ASSUME C on empty headers.
    asCPPHdr = [ 'c++', 'iostream', 'Qt', 'qt', 'qglobal.h', 'qcoreapplication.h' ];
    if asHeader:
        asCPPHdr.extend(asHeader);
    return any(h for h in asCPPHdr if h and any(c in h for c in asCPPHdr));

def getWinError(uCode):
    """
    Returns an error string for a given Windows error code.
    """
    FORMAT_MESSAGE_FROM_SYSTEM    = 0x00001000;
    FORMAT_MESSAGE_IGNORE_INSERTS = 0x00000200;

    wszBuf = ctypes.create_unicode_buffer(2048);
    dwBuf = ctypes.windll.kernel32.FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
                                                  None, uCode, 0, # Default language.
                                                  wszBuf, len(wszBuf), None);
    if dwBuf:
        return wszBuf.value.strip();
    return f'{uCode:#x}'; # Return the plain error (as hex).

def compileAndExecute(sName, enmBuildTarget, enmBuildArch, asIncPaths, asLibPaths, asIncFiles, asLibFiles, sCode, oEnv = None, fLog = True):
    """
    Compiles and executes a test program.

    Returns a tuple (Success, StdOut, StdErr).
    """
    _ = enmBuildArch;
    fRet = False;
    sStdOut = sStdErr = None;

    if enmBuildTarget == BuildTarget.WINDOWS:
        sCompiler = g_oEnv['config_cpp_compiler'];
    else:
        sCompiler = g_oEnv['config_cpp_compiler'] if hasCPPHeader(asIncFiles) else g_oEnv['config_c_compiler'];
    assert sCompiler is not None;

    if g_fDebug:
        sTempDir = tempfile.gettempdir();
    else:
        sTempDir = tempfile.mkdtemp();

    asFilesToDelete = []; # For cleanup

    sFileSource = os.path.join(sTempDir, "testlib.cpp" if ('g++' in sCompiler or 'cl.exe' in sCompiler) else "testlib.c"); ## @todo Improve this.
    asFilesToDelete.extend( [sFileSource] );
    sFileImage  = os.path.join(sTempDir, "a.out" if enmBuildTarget != BuildTarget.WINDOWS else "a.exe");
    asFilesToDelete.extend( [sFileImage] );

    with open(sFileSource, "w", encoding = 'utf-8') as fh:
        fh.write(sCode);
    fh.close();

    asCmd = [ sCompiler ];
    oProcEnv = oEnv if oEnv else g_oEnv;
    if g_fDebug:
        if enmBuildTarget == BuildTarget.WINDOWS:
            asCmd.extend( [ '/showIncludes' ]);
    if enmBuildTarget == BuildTarget.WINDOWS:
        if asIncPaths:
            for sIncPath in asIncPaths:
                oProcEnv.prependPath('INCLUDE', sIncPath);
        if asLibPaths:
            for sLibPath in asLibPaths:
                oProcEnv.prependPath('LIB', sLibPath);
        asCmd.extend( [ sFileSource ] );
        asCmd.extend( [ '/Fe:' + sFileImage ] );
    else: # Non-Windows
        if asIncPaths:
            for sIncPath in asIncPaths:
                asCmd.extend( [ f'-I{sIncPath}' ] );
        if asLibPaths:
            for sLibPath in asLibPaths:
                asCmd.extend( [ f'-L{sLibPath}' ] );
        asCmd.extend( [ sFileSource ] );
        asCmd.extend( [ '-o', sFileImage ] );
    asCmd.extend(getLinkerArgs(enmBuildTarget, asLibFiles));

    if g_fDebug:
        print(f'Process environment: {oProcEnv.env}');
        print(f'Process command line: {asCmd}');

    try:
        # Try compiling the test source file.
        oProc = subprocess.run(asCmd, env = oProcEnv.env, stdout = subprocess.PIPE, stderr = subprocess.PIPE, check = False, timeout = 15);
        if oProc.returncode != 0:
            sStdOut = oProc.stdout.decode("utf-8", errors="ignore"); # MSVC prints errors to stdout.
            sStdErr = oProc.stderr.decode("utf-8", errors="ignore");
            if fLog:
                printError(f'Compilation of test program for {sName} failed:', fDontCount = True);
                printError(f'    { " ".join(asCmd) }', fDontCount = True);
                printError(sStdOut, fDontCount = True);
                printError(sStdErr);
        else:
            # Try executing the compiled binary and capture stdout + stderr.
            try:
                oProc = subprocess.run([sFileImage], env = oProcEnv.env, shell = True, stdout = subprocess.PIPE, stderr = subprocess.PIPE, check = False, timeout = 10);
                if oProc.returncode == 0:
                    sStdOut = oProc.stdout.decode('utf-8', 'replace').strip();
                    fRet = True;
                else:
                    sStdErr = oProc.stderr.decode("utf-8", errors="ignore");
                    if fLog:
                        printError(f"Execution of test binary for {sName} failed with return code {oProc.returncode}:");
                        if enmBuildTarget == BuildTarget.WINDOWS:
                            printError(f"Windows Error { getWinError(oProc.returncode) }", fDontCount = True);
                        if sStdErr:
                            printError(sStdErr, fDontCount = True);
            except subprocess.SubprocessError as ex:
                if fLog:
                    printError(f"Execution of test binary for {sName} failed: {str(ex)}");
                    printError(f'    {sFileImage}', fDontCount = True);
    except PermissionError as e:
        printError(f'Compiler not found: {str(e)}', fDontCount = True);
    except FileNotFoundError as e:
        printError( 'Compiler not found:', fDontCount = True);
        printError(f'    { " ".join(asCmd) }', fDontCount = True);
        printError(str(e));
    except subprocess.SubprocessError as e:
        printError( 'Invoking compiler failed:', fDontCount = True);
        printError(f'    { " ".join(asCmd) }', fDontCount = True);
        printError(str(e));

    # Clean up.
    try:
        if not g_fDebug:
            for sFileToDel in asFilesToDelete:
                try:
                    os.remove(sFileToDel);
                except PermissionError:
                    pass;
            os.rmdir(sTempDir);
    except OSError as ex:
        if fLog:
            printVerbose(1, f"Failed to remove temporary files in '{sTempDir}': {str(ex)}");

    return fRet, sStdOut, sStdErr;

def getPackageInfo(sPackageName, sWhat):
    """
    Returns information for a given package.
    """
    try:
        if g_enmHostTarget in [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.DARWIN ]:
            # Use pkg-config on Linux and macOS.
            sCmd = f"pkg-config {sWhat} {shlex.quote(sPackageName)}"
        elif g_enmHostTarget == BuildTarget.WINDOWS:
            # Detect VCPKG.
            # See: https://learn.microsoft.com/en-us/vcpkg/ + https://vcpkg.io
            sCmd, _ = checkWhich('vcpkg');
            if sCmd:
                sVcPkgRoot = g_oEnv.get('config_vcpkg_root', os.environ['VCPKG_ROOT'] if 'VCPKG_ROOT' in os.environ else None);
                if sVcPkgRoot:
                    printVerbose(1, f"vcpkg found at '{sVcPkgRoot}'");
                else:
                    printError('vcpkg found, but VCPKG_ROOT is not defined');
        else:
            raise RuntimeError("Unsupported OS");

        oProc = subprocess.run(sCmd, shell = True, check = True, stdout = subprocess.PIPE, stderr = subprocess.PIPE, text =True);
        asLibs = oProc.stdout.strip();
        return True, asLibs;
    except subprocess.CalledProcessError:
        printVerbose(1, f'Package "{sPackageName}" invalid or not found');
        return False, None;
    return False, None;

def getPackageLibs(sPackageName):
    """
    Returns the libraries of a given package.
    """
    return getPackageInfo(sPackageName, '--libs');

def getPackagePath(sPackageName):
    """
    Returns the resource path of a given package.
    """
    return getPackageInfo(sPackageName, '--variable=exec_prefix');

class LibraryCheck:
    """
    Constructor.
    """
    def __init__(self, sName, asIncFiles, asLibFiles, aeTargets, sCode, aeTargetsExcluded = None, asAltIncFiles = None):
        self.sName = sName
        self.asIncFiles = asIncFiles or [];
        self.asLibFiles = asLibFiles or [];
        self.sCode = sCode;
        self.aeTargets = aeTargets;
        self.aeTargetsExcluded = aeTargetsExcluded if aeTargetsExcluded else [];
        self.asAltIncFiles = asAltIncFiles or [];
        self.fDisabled = False;
        self.sCustomPath = None;
        # Note: The first entry (index 0) always points to the library include path.
        #       The following indices are for auxillary header paths.
        self.asIncPaths = None;
        # Note: The first entry (index 0) always points to the library include path.
        #       The following indices are for auxillary header paths.
        self.asLibPaths = None;
        # Is a tri-state: None if not required (optional or not needed), False if required but not found, True if found.
        self.fHave = None;
        # Contains the (parsable) version string if detected.
        # Only valid if self.fHave is True.
        self.sVer = None;

    def getTestCode(self):
        """
        Return minimal program *with version print* for header check, per-library logic.
        """
        header = self.asIncFiles or (self.asAltIncFiles[0] if self.asAltIncFiles else None);
        if not header:
            return "";

        if self.sCode:
            if hasCPPHeader(self.asIncFiles):
                return '#include <iostream>\n' + self.sCode;
            else:
                return '#include <stdio.h>\n' + self.sCode;
        else:
            if hasCPPHeader(self.asIncFiles):
                return f"#include <{header}>\n#include <iostream>\nint main() {{ std::cout << \"1\" << std::endl; return 0; }}\n";
        return f'#include <{header}>\n#include <stdio.h>\nint main(void) {{ printf("<found>"); return 0; }}\n';

    def compileAndExecute(self, enmBuildTarget, enmBuildArch):
        """
        Attempts to compile and execute test code using the discovered paths and headers.

        Returns a tuple (Success, StdOut, StdErr).
        """
        fRc, sStdOut, sStdErr = compileAndExecute(self.sName, enmBuildTarget, enmBuildArch, \
                                                  self.asIncPaths, self.asLibPaths, self.asIncFiles, self.asLibFiles, self.getTestCode());
        if fRc and sStdOut:
            self.sVer = sStdOut;
        return fRc, sStdOut, sStdErr;

    def setArgs(self, args):
        """
        Applies argparse options for disabling and custom paths.
        """
        self.fDisabled = getattr(args, f"config_libs_disable_{self.sName}", False);
        self.sCustomPath = getattr(args, f"config_libs_path_{self.sName}", None);

    def getIncSearchPaths(self):
        """
        Returns a list of existing search directories for includes.
        """
        asPaths = [];

        # If a custom path has been specified (via '--with-<library>-path'), this has precedence.
        if self.sCustomPath:
            asPaths.extend([ self.sCustomPath ]);
        else: # Try our in-tree libs. We assume our checked-in stuff works! :-D
            asPaths.extend([ os.path.join(g_sScriptPath, 'src/libs', self.sName) ]);

        #
        # Windows
        #
        if  g_oEnv['KBUILD_TARGET'] == BuildTarget.WINDOWS:
            #
            # Try VCPKG first.
            #
            if g_oEnv['VCPKG_ROOT']:
                asPaths.extend([ os.path.join(g_oEnv['VCPKG_ROOT'], 'packages', self.sName) ]);
            #
            # Desperate fallback.
            #
            asRootDrivers = [ d+":" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(d+":") ];
            for r in asRootDrivers:
                asPaths.extend([ os.path.join(r, p) for p in [
                    "\\msys64\\mingw64\\include", "\\msys64\\mingw32\\include", "\\include" ]]);
                asPaths.extend([ r"c:\\Program Files", r"c:\\Program Files (x86)" ]);
        #
        # Linux / MacOS / Solaris
        #
        else:
            sGnuType = getLinuxGnuTypeFromPlatform();
            # Sorted by most likely-ness.
            asPaths.extend([ "/usr/include", "/usr/local/include",
                             "/usr/include/" + sGnuType, "/usr/local/include/" + sGnuType,
                             "/usr/include/" + self.sName, "/usr/local/include/" + self.sName,
                             "/opt/include", "/opt/local/include" ]);
            if  g_oEnv['KBUILD_TARGET'] == BuildTarget.DARWIN:
                asPaths.extend([ "/opt/homebrew/include" ]);
        #
        # Walk the custom path to guess where the include files are.
        #
        if self.sCustomPath:
            for sIncFile in self.asIncFiles:
                for sRoot, _, asFiles in os.walk(self.sCustomPath):
                    if sIncFile in asFiles:
                        asPaths = [ sRoot ] + asPaths;

        #
        # Some libs need IPRT, so include it.
        #
        asPaths.extend([ os.path.join(g_sScriptPath, 'include') ]);

        return [p for p in asPaths if os.path.isdir(p)];

    def getLibSearchPaths(self):
        """
        Returns a list of existing search directories for libraries.
        """
        asPaths = [];

        # If a custom path has been specified (via '--with-<library>-path'), this has precedence.
        if self.sCustomPath:
            asPaths = [os.path.join(self.sCustomPath, 'lib')];

        # Try our in-tree libs first.
        asPaths.extend([ os.path.join(g_sScriptPath, 'src/libs', self.sName) ]);

        #
        # Windows
        #
        if  g_oEnv['KBUILD_TARGET'] == BuildTarget.WINDOWS:
            #
            # Try VCPKG first.
            #
            if g_oEnv['VCPKG_ROOT']:
                asPaths.extend([ os.path.join(g_oEnv['VCPKG_ROOT'], 'packages', self.sName) ]);
            #
            # Desperate fallback.
            #
            asRootDrives = [d+":" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(d+":")];
            for r in asRootDrives:
                asPaths += [os.path.join(r, p) for p in [
                    '\\msys64\\mingw64\\lib', '\\msys64\\mingw32\\lib', '\\lib']];
                asPaths += [r'c:\\Program Files', r'c:\\Program Files (x86)'];
        #
        # Linux / MacOS / Solaris
        #
        else:  # Linux / MacOS / Solaris
            if  g_oEnv['KBUILD_TARGET'] == BuildTarget.LINUX \
            or  g_oEnv['KBUILD_TARGET'] == BuildTarget.SOLARIS:
                sGnuType = getLinuxGnuTypeFromPlatform();
                # Sorted by most likely-ness.
                asPaths.extend([ "/usr/lib", "/usr/local/lib",
                                 "/usr/lib/" + sGnuType, "/opt/local/lib/" + sGnuType,
                                 "/usr/lib64", "/lib", "/lib64",
                                 "/opt/lib", "/opt/local/lib" ]);
            else: # Darwin
                asPaths.append("/opt/homebrew/lib");
        #
        # Walk the custom path to guess where the lib files are.
        #
        if self.sCustomPath:
            for sLibFile in self.asLibFiles:
                for sRoot, _, asFiles in os.walk(self.sCustomPath):
                    if sLibFile in asFiles:
                        asPaths = [ sRoot ] + asPaths;

        return [p for p in asPaths if os.path.exists(p)];

    def checkInc(self):
        """
        Checks for headers in standard/custom include paths.
        """
        if not self.asIncFiles and not self.asAltIncFiles:
            return True;
        asHeaderToSearch = [];
        if self.asIncFiles:
            asHeaderToSearch.extend(self.asIncFiles);
        asHeaderToSearch.extend(self.asAltIncFiles);
        asHeaderFound = [];
        asSearchPaths = self.getIncSearchPaths();
        for sCurHeader in asHeaderToSearch:
            for sCurSearchPath in asSearchPaths:
                printVerbose(1, f"{self.sName}: Checking include path for '{sCurHeader}': {sCurSearchPath}");
                if os.path.isfile(os.path.join(sCurSearchPath, sCurHeader)):
                    if os.sep == "\\":
                        sCurSearchPath = sCurSearchPath.replace("/", "\\");
                    if not self.asIncPaths:
                        self.asIncPaths = [];
                    self.asIncPaths.extend([ sCurSearchPath ]);
                    asHeaderFound.extend([ sCurHeader ]);
                    break;

        if asHeaderFound == asHeaderToSearch:
            printVerbose(1, f"{self.sName}: All header files found");
            return True;

        printError(f"{self.sName}: Header files {asHeaderToSearch} not found in paths: {asSearchPaths}");
        return False;

    def checkLib(self):
        """
        Checks for libraries in standard/custom lib paths.
        """
        if not self.asLibFiles:
            return True;
        asLibToSearch = self.asLibFiles;
        asLibExts = [];
        if  g_oEnv['KBUILD_TARGET'] == BuildTarget.WINDOWS:
            asLibExts = ['.lib', '.dll', '.a', '.dll.a'];
        elif  g_oEnv['KBUILD_TARGET'] == BuildTarget.DARWIN:
            asLibExts = ['.a', '.dylib', '.so'];
        else:
            asLibExts = ['.a', '.so'];
        asLibFound = [];
        asSearchPaths = self.getLibSearchPaths();
        for sCurSearchPath in asSearchPaths:
            printVerbose(1, f'{self.sName}: Checking library path: {sCurSearchPath}');
            for sCurLib in asLibToSearch:
                for sCurExt in asLibExts:
                    sPattern = os.path.join(sCurSearchPath, f"{sCurLib}*{sCurExt}");
                    for sCurFile in glob.glob(sPattern):
                        if os.path.isfile(sCurFile):
                            if not self.asLibPaths:
                                self.asLibPaths = [];
                            self.asLibPaths.extend([ sCurSearchPath ]);
                            return True;

        if asLibFound == asLibToSearch:
            printVerbose(1, f"{self.sName}: All libraries found");
            return True;

        printError(f"{self.sName}: Library files { ' '.join(asLibToSearch)} not found in paths: {asSearchPaths}");
        return False;

    def performCheck(self):
        """
        Run library detection.
        """
        if  g_oEnv['KBUILD_TARGET'] in self.aeTargetsExcluded:
            return True;
        if self.fDisabled:
            return True;
        # Check if no custom path was specified and we have the lib in-tree.
        if not self.sCustomPath:
            sInTreePath = os.path.join(g_sScriptPath, 'src/libs', self.sName + '-*');
            asPatternMatches = glob.glob(sInTreePath);
            for sCurMatch in asPatternMatches:
                print(f"{self.sName}: Found library in-tree at '{sCurMatch}', skipping check");
                self.fHave = True;
                # Extract the version from the directory name.
                oReMatch = re.search(r'-([\d\.]+)$', os.path.basename(os.path.normpath(sCurMatch)));
                if oReMatch:
                    self.sVer = oReMatch.group(1);
                if not self.asIncPaths:
                    self.asIncPaths = [];
                self.asIncPaths.extend([ os.path.relpath(sCurMatch, g_sScriptPath) ]); # Make the path relative to the script.
                return True; # ASSUMES that we only have one version per lib in-tree.
        self.fHave = False;
        if  g_oEnv['KBUILD_TARGET'] in self.aeTargets \
        or BuildTarget.ANY in self.aeTargets:
            print(f"{self.sName}: Testing library ...");
            if self.checkInc():
                if self.checkLib():
                    self.fHave, _, _ = self.compileAndExecute(g_oEnv['KBUILD_TARGET'], g_oEnv['KBUILD_TARGET_ARCH']);
            if not self.fHave:
                printError(f"{self.sName}: Library not found");
        return self.fHave;

    def getStatusString(self):
        """
        Return string indicator: yes, no, DISABLED, or - (not checked / disabled / whatever).
        """
        if self.fDisabled:
            return "DISABLED";
        elif self.fHave:
            return "ok";
        elif self.fHave is None:
            return "?";
        else:
            return "failed";

    def __repr__(self):
        return f"{self.sName}: {self.getStatusString()}";

class ToolCheck:
    """
    Describes and checks for a build tool.
    """
    def __init__(self, sName, asCmd = None, fnCallback = None, aeTargets = None):
        """
        Constructor.
        """
        assert sName;

        self.sName = sName;
        self.fnCallback = fnCallback;
        self.aeTargets = [ BuildTarget.ANY ] if aeTargets is None else aeTargets;
        self.fDisabled = False;
        self.sCustomPath = None;
        # Is a tri-state: None if not required (optional or not needed), False if required but not found, True if found.
        self.fHave = None;
        # List of command names (binaries) to check for.
        # A tool can have multiple binaries.
        self.asCmd = asCmd;
        # Path to the found command.
        # Only valid if self.fHave is True.
        self.sCmdPath = None;
        # Contains the (parsable) version string if detected.
        # Only valid if self.fHave is True.
        self.sVer = None;

    def setArgs(self, oArgs):
        """
        Apply argparse options for disabling the tool.
        """
        self.fDisabled = getattr(oArgs, f"config_tools_disable_{self.sName}", False);
        self.sCustomPath = getattr(oArgs, f"config_tools_path_{self.sName}", None);

    def performCheck(self):
        """
        Performs the actual check of the tool.

        Returns success status.
        """
        if self.fDisabled:
            self.fHave = None;
            return True;
        if g_oEnv['KBUILD_TARGET'] in self.aeTargets \
        or BuildTarget.ANY in self.aeTargets:
            self.fHave = False;
            print(f"{self.sName}: Checking ...");
            if self.fnCallback: # Custom callback function provided?
                self.fHave = self.fnCallback(self);
            else:
                for sCmdCur in self.asCmd:
                    self.sCmdPath, self.sVer = checkWhich(sCmdCur, self.sName, self.sCustomPath);
                    if self.sCmdPath:
                        self.fHave = True;
            if not self.fHave:
                printError(f"{self.sName}: Tool not found");
        return self.fHave;

    def getStatusString(self):
        """
        Returns a string for the tool's status.
        """
        if self.fDisabled:
            return 'DISABLED';
        if self.fHave:
            return f'ok ({os.path.basename(self.sCmdPath)})' if self.sCmdPath else 'ok';
        if self.fHave is None:
            return '?';
        return "failed";

    def __repr__(self):
        return f"{self.sName}: {self.getStatusString()}"

    def getWinProgramFiles(self):
        """
        Returns a list of existing Windows "Program Files" directories.

        @todo Cache this?
        """
        asPaths = [];
        for sEnv in [ 'ProgramFiles', r'C:\Program File', \
                      'ProgramFiles(x86)', r'C:\Program Files (x86)',
                      'ProgramFiles(Arm)', r'C:\Program Files (Arm)' ]:
            sPath = os.environ.get(sEnv);
            if sPath and os.path.exists(sPath):
                asPaths.extend([ sPath ]);

        if 'programfiles' in g_asPathsPrepend:
            asPaths = g_asPathsPrepend['programfiles'] + asPaths;
        if 'programfiles' in g_asPathsAppend:
            asPaths.extend(g_asPathsAppend['programfiles']);

        return asPaths;

    def checkCallback_GSOAP(self):
        """
        Checks for the GSOAP compiler. Needed for the webservices.
        """

        asLibs = None;
        sPath = None; # Acts as the 'found' beacon.
        sPathImport = None;
        sPathSource = None;

        if     not g_oEnv['VBOX_PATH_GSOAP'] \
           and not g_oEnv['VBOX_PATH_GSOAP_IMPORRT']:
            fRc, asLibs,  = getPackageLibs('gsoapssl++');
            if fRc:
                fRc, sPath,  = getPackagePath('gsoapssl++');

        if not sPath: # Try in dev tools.
            asDevPaths = sorted(glob.glob(f'{g_sDevPath}/common/gsoap/v*'));
            for sDevPath in asDevPaths:
                if os.path.exists(sDevPath):
                    sPath = sDevPath;

        if not sPath: # Still not found? Try other stuff.
            sBin1, _  = checkWhich('soapcpp2');
            sBin2, _  = checkWhich('wsdl2h');
            ## @todo Check for libgsoap++.a/so
            if os.path.dirname(sBin1) == os.path.dirname(sBin2):
                sPath = os.path.dirname(sBin1);
                if sPath.startswith('/usr/'):
                    sPathImport = os.path.join('/usr', 'share/gsoap/import');

        if sPath:
            sPathImport = os.path.join(sPath, 'share/gsoap/import');
            sPathSource = os.path.join(sPath, 'share/gsoap/stdsoap2.cpp');
            if not os.path.isfile(sPathSource):
                sPathSource = None;

        g_oEnv.set('VBOX_GSOAP_INSTALLED', '1' if sPath else None);
        g_oEnv.set('VBOX_PATH_GSOAP', sPath);
        g_oEnv.set('VBOX_PATH_GSOAP_IMPORT', sPathImport if sPath else None);
        g_oEnv.set('VBOX_GSOAP_CXX_SOURCES', sPathSource if sPath else None);
        g_oEnv.set('VBOX_GSOAP_CXX_LIBS', asLibs if sPath else None);

        return True if sPath else False;

    def checkCallback_VisualCPP(self):
        """
        Checks for Visual C++ Build Tools 16 (2019), 15 (2017), 14 (2015), 12 (2013), 11 (2012) or 10 (2010).
        """

        # Since v2017 we can use vswhere.exe, so try using that first.
        sVCPPVer = None;
        sVCPPPath = None;
        for sProgramPath in self.getWinProgramFiles():
            sPath = os.path.join(sProgramPath, 'Microsoft Visual Studio', 'Installer', 'vswhere.exe');
            if os.path.isfile(sPath):
                # Stupid vswhere can't handle multiple properties at once, so we have to deal with it
                # by calling it multiple times. Joy.
                asProps = [ 'installationVersion', 'installationPath', 'displayName' ];
                for sCurProp in asProps:
                    asCmd = [ sPath,
                             '-sort', # Sort newest version first.
                             '-products', '*',
                             '-requires', 'Microsoft.VisualStudio*',
                             '-property', sCurProp,
                             '-format', 'json' ];
                    oProc = subprocess.run(asCmd, capture_output = True, check = False, text = True);
                    if oProc.returncode == 0 and oProc.stdout.strip():
                        import json
                        asList = json.loads(oProc.stdout);
                        for curProd in asList:
                            if sCurProp == 'installationVersion':
                                sVCPPVer = curProd.get('installationVersion', None);
                            if sCurProp == 'installationPath':
                                sVCPPPath = curProd.get('installationPath', None);
                            if sCurProp == 'displayName':
                                printVerbose(1, f"Found {curProd.get('displayName', '')} version {sVCPPVer} at '{sVCPPPath}'");

                if not g_fDebug:
                    break;

            if sVCPPVer:
                break;

        # For older versions we have to use the registry. Start with "newest" first.
        if not sVCPPVer:
            import winreg
            for uVer, sName in [(14, "2015"), (12, "2013"), (11, "2012"), (10, "2010")]:
                try:
                    sVer = r'SOFTWARE\Microsoft\VisualStudio\{}.0\Setup\VC'.format(uVer);
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sVer) as k:
                        sVCPPPath, _ = winreg.QueryValueEx(k, "ProductDir");
                        sVCPPVer     = sName;
                        break;
                except FileNotFoundError:
                    pass;

        if sVCPPVer:
            print(f"Found Visual C++ version {sVCPPVer} at '{sVCPPPath}'");

            sVCPPPath = os.path.join(sVCPPPath, 'VC', 'Tools', 'MSVC');
            asVCPPVer = sorted(glob.glob(os.path.join(sVCPPPath, '*')), reverse = True);
            for sVer in asVCPPVer:
                sVCPPPath = os.path.join(sVCPPPath, sVer);

            mapVsToolsScheme = {
                ## @todo Anything older we support?
                "14.0"      : ("14.0.xxxxx",       "VCC140", "Visual Studio 2015 (initial)"),
                "15.0-15.2" : ("14.10.xxxxx",      "VCC141", "Visual Studio 2017 (initial)"),
                "15.3"      : ("14.11.xxxxx",      "VCC141", "Visual Studio 2017 Update 3"),
                "15.5"      : ("14.12.xxxxx",      "VCC141", "Visual Studio 2017 Update 5"),
                "15.6"      : ("14.13.xxxxx",      "VCC141", "Visual Studio 2017 Update 6"),
                "15.7"      : ("14.14.xxxxx",      "VCC141", "Visual Studio 2017 Update 7"),
                "15.8"      : ("14.15.xxxxx",      "VCC141", "Visual Studio 2017 Update 8"),
                "15.9"      : ("14.16.xxxxx",      "VCC141", "Visual Studio 2017 Update 9"),
                "16.0"      : ("14.20.xxxxx",      "VCC142", "Visual Studio 2019 (initial)"),
                "16.1-16.11": ("14.21–14.29.xxxxx","VCC142", "Visual Studio 2019 Updates"),
                "17.0"      : ("14.30.xxxxx",      "VCC143", "Visual Studio 2022 (initial)"),
                "17.x"      : ("14.3x.xxxxx",      "VCC143", "Visual Studio 2022 Updates")
            };

            sVCPPVer = '.'.join(sVCPPVer.split('.')[:2]); # Strip build #.
            sPattern = sVCPPVer;
            if not any(c in sPattern for c in '*?[]'):
                sPattern += '*';
            asMatches = [];
            # Match all versions.
            for sVer, (sToolset, sScheme, sDesc) in mapVsToolsScheme.items():
                sFirstVer = sVer.split('-', maxsplit = 1)[0];
                if fnmatch.fnmatch(sFirstVer, sPattern):
                    asMatches.append((sVer, sToolset, sScheme, sDesc));

            if asMatches:
                # Process all versions matched.
                for _, _, sScheme, sDesc in asMatches:

                    # Warn if not the current version we're going to use by default.
                    if int(sScheme.replace("VCC", "")) < 143:
                        printWarn(f'Warning: Found unsupported {sDesc}, but it may work');

                    # Construct paths.
                    mapArch2Dir = {
                        BuildArch.X86  : 'x86',
                        BuildArch.AMD64: 'x64',
                        BuildArch.ARM64: 'arm64'
                    };
                    g_oEnv.set(f'PATH_TOOL_{sScheme}', sVCPPPath);
                    for sArch, sDirName in mapArch2Dir.items():
                        sVCPPBinDir = os.path.join(sVCPPPath, f'Host{sDirName}', sDirName, 'bin');
                        g_oEnv.set(f'PATH_TOOL_{sScheme}{sArch.upper()}', sVCPPBinDir);
                        if g_oEnv['KBUILD_TARGET_ARCH'] == sArch:
                            # Make sure that we have cl.exe in our path so that we can use it for tests compilation lateron.
                            g_oEnv.prependPath('PATH', sVCPPBinDir);
                            # Same goes for the libs.
                            g_oEnv.prependPath('LIB', os.path.join(sVCPPPath, 'lib', sDirName));
            else:
                printWarn(f'Warning: Found unsupported Visual C++ version {sVCPPVer}, but it may work');

            ## @todo Fix this.
            g_oEnv.prependPath('INCLUDE', r'C:\Program Files (x86)\Microsoft Visual Studio\2017\Community\VC\Tools\MSVC\14.16.27023\include');
            g_oEnv.prependPath('INCLUDE', r'c:\Program Files (x86)\Windows Kits\10\Include\10.0.19041.0\ucrt');
            g_oEnv.prependPath('INCLUDE', r'c:\Program Files (x86)\Windows Kits\10\Include\10.0.19041.0\shared');
            g_oEnv.prependPath('LIB', r'C:\Program Files (x86)\Microsoft Visual Studio\2017\BuildTools\VC\Tools\MSVC\14.16.27023\lib\x64');
            g_oEnv.prependPath('LIB', r'C:\Program Files (x86)\Windows Kits\10\Lib\10.0.19041.0\ucrt\x64');
            g_oEnv.prependPath('LIB', r'C:\Program Files (x86)\Windows Kits\10\Lib\10.0.19041.0\um\x64');

            g_oEnv.set('config_c_compiler', 'cl.exe');
            g_oEnv.set('config_cpp_compiler', 'cl.exe');

        return True if sVCPPVer else False;

    def getHighestVersionDir(self, sPath):
        """
        Finds the directory with the highest version number in the given path.
        """
        asVer = [];
        for sCurPath in os.listdir(sPath):
            sPathFull = os.path.join(sPath, sCurPath);
            if os.path.isdir(sPathFull):
                try:
                    # Strip any number prefixes.
                    m = re.match(r'^(?:v|[ver]sion[\-_]?|release)?([0-9].*)$', sCurPath, re.IGNORECASE);
                    sCurPathStripped = m.group(1) if m else sCurPath;
                    asParts = re.split(r'[\.\-]', sCurPathStripped);
                    asVerParts = [];
                    for sPart in asParts:
                        m = re.match(r'(\d+)(.*)', sPart)
                        if m:
                            asVerParts.append(int(m.group(1)));
                            if m.group(2):
                                asVerParts.append(m.group(2));
                        else:
                            asVerParts.append(sPart);
                    sVerTuple = tuple(asVerParts);
                    asVer.append((sVerTuple, sPathFull));
                except ValueError:
                    pass;

        # Get the entry with the highest version tuple.
        return max(asVer) if asVer else (None, None);

    def checkCallback_Win10SDK(self):
        """
        Checks for Windows 10 SDK.
        """

        # Check our tools first.
        sSDKVer, sSDKPath = self.getHighestVersionDir(os.path.join(g_sScriptPath, 'tools', 'win.x86', 'sdk'));
        if sSDKVer:
            sSDKVer = '.'.join(str(s) for _, s in enumerate(sSDKVer));
        else:
            try:
                import winreg;
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    r"SOFTWARE\Microsoft\Windows Kits\Installed Roots") as oKey:

                    sSDKPath, _ = winreg.QueryValueEx(oKey, "KitsRoot10");
                    printVerbose(1, f"Found Windows 10 SDK at '{sSDKPath}'");

                    sPathInc = os.path.join(sSDKPath, "Include");
                    if not os.path.isdir(sPathInc):
                        printVerbose(1, f"Windows 10 SDK Include path not found in '{sPathInc}'");
                    else:
                        asVersions = [];
                        for sCurPath in os.listdir(sPathInc):
                            sPathVer = os.path.join(sPathInc, sCurPath);
                            if os.path.isdir(sPathVer) and sCurPath[0].isdigit():
                                asVersions.append(sCurPath);

                        # Sort by version (splitting at '.' and converting to ints);
                        if asVersions:
                            asVersions.sort(key=lambda v: [int(sPart) for sPart in v.split('.')], reverse = True);
                            sSDKVer = asVersions[0];

            except FileNotFoundError as ex:
                printVerbose(1, f'Could not find Windows 10 SDK path in registry: {ex}');
            finally:
                pass;

        if sSDKPath:
            g_oEnv.set('PATH_SDK_WINSDK10', sSDKPath);
            g_oEnv.set('SDK_WINSDK10_VERSION', sSDKVer);
            self.sVer = sSDKVer;
            self.sCmdPath = sSDKPath;

        return True if sSDKVer else False;

    def checkCallback_WinDDK(self):
        """
        Checks for the Windows DDK/WDK.
        """

        # Check our tools first.
        sDDKVer, sDDKPath = self.getHighestVersionDir(os.path.join(g_sScriptPath, 'tools', 'win.x86', 'ddk'));
        if sDDKVer:
            sDDKVer = '.'.join(str(s) for _, s in enumerate(sDDKVer));
        else:
            asVer = [];
            asRegKey = [
                r"SOFTWARE\Microsoft\Windows Kits\WDK",
                r"SOFTWARE\Wow6432Node\Microsoft\WINDDK" # Legacy DDKs.
            ];

            import winreg;
            for sCurKey in asRegKey:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sCurKey) as key:
                        uIdx = 0;
                        while True:
                            try:
                                sSubKey = winreg.EnumKey(key, uIdx);
                                with winreg.OpenKey(key, sSubKey) as oSubKey:
                                    sPath, _ = winreg.QueryValueEx(oSubKey, "InstallationFolder");
                                    if os.path.exists(sPath):
                                        asVer.append((sSubKey, sPath));
                                        printVerbose(1, "{self.sName}: Found directroy in registry '{sPath}'");
                                uIdx += 1;
                            except OSError:
                                break;
                except FileNotFoundError:
                    continue;

            asDir = [
                r"C:\Program Files (x86)\Windows Kits\10",
                r"C:\WINDDK"
            ];

            for sCurDir in asDir:
                if os.path.isdir(sCurDir):
                    for sPath in os.listdir(sCurDir):
                        sPathAbs = os.path.join(sCurDir, sPath);
                        if   os.path.isdir(sPathAbs) \
                        and (sPathAbs.lower().startswith("wdk") or sPathAbs[0].isdigit()):
                            asVer.append((sPathAbs, sPathAbs));
                            printVerbose(1, "{self.sName}: Found file system directroy '{sPathAbs}'");

            # Find 7600.16385.1 (Windows 7 Driver Development Kit, also for Server 2008 R2).
            if asVer:
                for sCurPath, _ in asVer:
                    asFiles = [
                        "inc/api/ntdef.h",
                        "lib/win7/i386/int64.lib",
                        "lib/wlh/i386/int64.lib",
                        "lib/wnet/i386/int64.lib",
                        "lib/wxp/i386/int64.lib",
                        "bin/x86/rc.exe"
                    ];
                    for sFile in asFiles:
                        if not os.path.exists(os.path.join(sCurPath, sFile)):
                            printError("{self.sName}: File '{sFile} not found in '{sCurPath}'");
                            return False;

        if sDDKVer:
            g_oEnv.set('PATH_SDK_WINDDK71', sDDKPath);
            g_oEnv.set('SDK_WINDDK71_VERSION', sDDKVer);
            self.sVer = sDDKVer;
            self.sCmdPath = sDDKPath;

        return True if sDDKVer else False;

    def checkCallback_kBuild(self):
        """
        Checks for kBuild stuff and sets the paths.
        """

        #
        # Git submodules can only mirror whole repositories, not sub directories,
        # meaning that kBuild is residing a level deeper than with svn externals.
        #
        fFound = False;

        if not g_oEnv['KBUILD_PATH']:
            sPath = os.path.join(g_sScriptPath, 'kBuild/kBuild');
            if not os.path.exists(sPath):
                sPath = os.path.join(g_sScriptPath, 'kBuild');
            sPathTgt = os.path.join(sPath, 'bin', g_oEnv['KBUILD_TARGET'] + "." + g_oEnv['KBUILD_TARGET_ARCH']);
            if os.path.exists(sPathTgt):
                if  checkWhich('kmk', 'kBuild kmk', sPathTgt) \
                and checkWhich('kmk_ash', 'kBuild kmk_ash', sPathTgt) \
                and os.path.isfile(os.path.join(sPath, 'footer.kmk')) \
                and os.path.isfile(os.path.join(sPath, 'header.kmk')) \
                and os.path.isfile(os.path.join(sPath, 'rules.kmk')):
                    g_oEnv.set('KBUILD_PATH', sPath);
                    self.sCmdPath = g_oEnv['KBUILD_PATH'];
                    fFound = True;

        # If KBUILD_DEVTOOLS is set, check that it's pointing to something useful.
        sPathDevTools = os.environ.get('KBUILD_DEVTOOLS');
        if not sPathDevTools:
            sPathDevTools = os.path.join(sPath, 'tools');
            sPathDevTools = sPathDevTools if os.path.exists(sPathDevTools) else None;
        if sPathDevTools:
            print(f"kBuild devtools is set to '{sPathDevTools}'");
            fFound = True if os.path.isfile(os.path.join(sPathDevTools, 'ZIP.kmk')) else False; # Check for some random tool.
        else: ## @todo Is this fatal?
            printVerbose(1, 'kBuild devtools not found!');

        return fFound;

    def checkCallback_gcc(self):
        """
        Checks for gcc.
        """
        class gccTools:
            """ Structure for the GCC tools. """
            def __init__(self, name, switches):
                self.sName = name;
                self.asVerSwitches = switches;
                self.sVer = None;
                self.sPath = None;
        asToolsToCheck = {
            'gcc' : gccTools( "gcc", [ '-dumpfullversion', '-dumpversion' ] ),
            'g++' : gccTools( "g++", [ '-dumpfullversion', '-dumpversion' ] )
        };

        for _, (sName, curEntry) in enumerate(asToolsToCheck.items()):
            asToolsToCheck[sName].sPath, asToolsToCheck[sName].sVer = \
                checkWhich(curEntry.sName, curEntry.sName, asVersionSwitches = curEntry.asVerSwitches);
            if not asToolsToCheck[sName].sPath:
                printError(f'{curEntry.sName} not found');
                return False;

        if asToolsToCheck['gcc'].sVer != asToolsToCheck['g++'].sVer:
            printError('GCC and G++ versions do not match!');
            return False;

        g_oEnv.set('CC32',  os.path.basename(asToolsToCheck['gcc'].sPath));
        g_oEnv.set('CXX32', os.path.basename(asToolsToCheck['g++'].sPath));
        if g_enmHostArch == BuildArch.AMD64:
            g_oEnv.append('CC32',  ' -m32');
            g_oEnv.append('CXX32', ' -m32');
        elif g_enmHostArch == BuildArch.X86 \
        and  g_oEnv['KBUILD_TARGET_ARCH'] == BuildArch.AMD64: ## @todo Still needed?
            g_oEnv.append('CC32',  ' -m64');
            g_oEnv.append('CXX32', ' -m64');
        elif g_oEnv['KBUILD_TARGET_ARCH'] == BuildArch.AMD64:
            g_oEnv.unset('CC32');
            g_oEnv.unset('CXX32');

        sCC = os.path.basename(asToolsToCheck['gcc'].sPath);
        if sCC != 'gcc':
            g_oEnv.set('TOOL_GCC3_CC', sCC);
            g_oEnv.set('TOOL_GCC3_AS', sCC);
            g_oEnv.set('TOOL_GCC3_LD', sCC);
            g_oEnv.set('TOOL_GXX3_CC', sCC);
            g_oEnv.set('TOOL_GXX3_AS', sCC);
        sCXX = os.path.basename(asToolsToCheck['g++'].sPath);
        if sCXX != 'gxx':
            g_oEnv.set('TOOL_GCC3_CXX', sCXX);
            g_oEnv.set('TOOL_GXX3_CXX', sCXX);
            g_oEnv.set('TOOL_GXX3_LD' , sCXX);

        sCC32 = g_oEnv['CC32'];
        if  sCC32 != 'gcc -m32' \
        and sCC32 != '':
            g_oEnv.set('TOOL_GCC3_CC', sCC32);
            g_oEnv.set('TOOL_GCC3_AS', sCC32);
            g_oEnv.set('TOOL_GCC3_LD', sCC32);
            g_oEnv.set('TOOL_GXX3_CC', sCC32);
            g_oEnv.set('TOOL_GXX3_AS', sCC32);

        sCXX32 = g_oEnv['CXX32'];
        if  sCXX32 != 'g++ -m32' \
        and sCXX32 != '':
            g_oEnv.set('TOOL_GCC32_CXX', sCXX32);
            g_oEnv.set('TOOL_GXX32_CXX', sCXX32);
            g_oEnv.set('TOOL_GXX32_LD' , sCXX32);

        sCC64  = g_oEnv['CC64'];
        sCXX64 = g_oEnv['CXX64'];
        g_oEnv.set('TOOL_Bs3Gcc64Elf64_CC', sCC64 if sCC64 else sCC);
        g_oEnv.set('TOOL_Bs3Gcc64Elf64_CXX', sCXX64 if sCXX64 else sCXX);

        # Solaris sports a 32-bit gcc/g++.
        if  g_oEnv['KBUILD_TARGET']      == BuildTarget.SOLARIS \
        and g_oEnv['KBUILD_TARGET_ARCH'] == BuildArch.AMD64:
            g_oEnv.set('CC' , 'gcc -m64' if sCC == 'gcc' else None);
            g_oEnv.set('CXX', 'gxx -m64' if sCC == 'gxx' else None);

        self.sCmdPath = asToolsToCheck['gcc'].sPath;
        self.sVer     = asToolsToCheck['gcc'].sVer;

        g_oEnv.set('config_c_compiler', 'gcc');   ## @todo Fix this.
        g_oEnv.set('config_cpp_compiler', 'g++');
        return True;

    def checkCallback_devtools(self):
        """
        Checks for devtools and sets the paths.
        """

        if not g_oEnv['KBUILD_DEVTOOLS']:
            sPath = os.path.join(g_sScriptPath, 'tools');
            if os.path.exists(sPath):
                sPath = os.path.join(sPath, g_oEnv['KBUILD_TARGET'] + "." + g_oEnv['KBUILD_TARGET_ARCH']);
                if os.path.exists(sPath):
                    g_oEnv.set('KBUILD_DEVTOOLS', sPath);
                    self.sCmdPath = g_oEnv['KBUILD_DEVTOOLS'];
                    return True;
        return True; ## @todo Not critical?

    def checkCallback_OpenWatcom(self):
        """
        Checks for OpenWatcom tools.
        """

        # These are the sub directories OpenWatcom ships its binaries in.
        mapBuildTarget2Bin = {
            BuildTarget.DARWIN:  "binosx",  ## @todo Still correct for Apple Silicon?
            BuildTarget.LINUX:   "binl64" if g_oEnv['KBUILD_TARGET_ARCH'] is BuildArch.AMD64 else "arml64", # ASSUMES 64-bit.
            BuildTarget.SOLARIS: "binsol",  ## @todo Test on Solaris.
            BuildTarget.WINDOWS: "binnt",
            BuildTarget.BSD:     "binnbsd"  ## @todo Test this on FreeBSD.
        };

        sBinSubdir = mapBuildTarget2Bin.get(g_oEnv['KBUILD_TARGET'], None);
        if not sBinSubdir:
            printError(f"OpenWatcom not supported on host target { g_oEnv['KBUILD_TARGET'] }.");
            return False;

        for sCmdCur in self.asCmd:
            self.sCmdPath, self.sVer = checkWhich(sCmdCur, 'OpenWatcom', os.path.join(self.sCustomPath, sBinSubdir) if self.sCustomPath else None);
            if not self.sCmdPath:
                return False;

        return True;

    def checkCallback_PythonC_API(self):
        """
        Checks for required Python C API development files.
        """

        # On darwin (macOS), just enable Python support.
        if g_enmHostTarget == BuildTarget.DARWIN:
            return True;

        # Due to Windows App sandboxing and permissions, the include directory returned by a Python installation
        # from the Microsoft Store (or App packages) will point to the inaccessible WindowsApp directory.
        # So detect that and refuse to continue.
        asPathInc = sysconfig.get_paths()[ 'include' ];
        if not asPathInc:
            printError('Python installation invalid (include path) not found');
            return False;
        if '\\WindowsApps\\' in asPathInc: # Lazy me.
            printError('Incompatible Python installation detected (placed in WindowsApps directory), can\'t continue');
            return False;

        sCode = """
#include <Python.h>
int main()
{
    Py_Initialize();
    Py_Finalize();
    return 0;
}""";
        sLibDir = sysconfig.get_config_var("LIBDIR");
        sLdLib  = sysconfig.get_config_var("LDLIBRARY");
        if sLdLib.endswith('.so'):
            sLdLib = sLdLib[:-3]; # Strip .so ending.
        elif sLdLib.endswith('.dll'):
            sLdLib = sLdLib[:-4]; # Strip .dll ending.

        # Make sure that the Python .dll / .so files are in PATH.
        g_oEnv.prependPath('PATH', sysconfig.get_paths()[ 'data' ]);

        if compileAndExecute('Python Dev', g_enmHostTarget, g_enmHostArch, [ asPathInc ], [ sLibDir ], [ ], [ sLdLib ], sCode):
            g_oEnv.set('VBOX_WITH_PYTHON', '1' if asPathInc else None);
            g_oEnv.set('VBOX_PATH_PYTHON_INC', asPathInc);
            g_oEnv.set('VBOX_LIB_PYTHON', sLibDir);
            return True;

        return False;

    def checkCallback_PythonModules(self):
        """
        Checks for required Python modules installed.
        """
        fFound = True;
        asModulesToCheck = [ 'packaging' ];

        for asCurMod in asModulesToCheck:
            try:
                importlib.import_module(asCurMod);
                printVerbose(1, f"Python module '{asCurMod}'' is installed");
            except ImportError:
                printError(f"Python module '{asCurMod}' is not installed");
                printError(f"Hint: Try running 'pip install {asCurMod}'", fDontCount=True);
                fFound = False;
                if not g_fContOnErr:
                    return fFound;

        return fFound;


    def checkCallback_XCode(self):
        """
        Checks for Xcode and Command Line Tools on macOS.
        """

        asPathsToCheck = [];
        if self.sCustomPath:
            asPathsToCheck.append(self.sCustomPath);

        #
        # Detect Xcode.
        #
        asPathsToCheck.extend([
            '/Library/Developer/CommandLineTools'
        ]);

        for sPathCur in asPathsToCheck:
            if os.path.isdir(sPathCur):
                sPathClang      = os.path.join(sPathCur, 'usr/bin/clang');
                sPathXcodebuild = os.path.join(sPathCur, 'usr/bin/xcodebuild');
                printVerbose(1, ('Checking for CommandLineTools at:', sPathCur));
                if  os.path.isfile(sPathClang) \
                and os.path.isfile(sPathXcodebuild):
                    print('Found CommandLineTools at:', sPathCur);
                    self.sCmdPath = sPathXcodebuild;
                    return True;

        printError('CommandLineTools not found.');
        return False;

class EnvManager:
    """
    A simple manager for environment variables.
    """

    def __init__(self):
        """
        Initializes an environment variable store with the default environment applied.
        """
        self.env = os.environ.copy();

    def set(self, sKey, sVal):
        """
        Set the value for a given environment variable key.
        Empty values are allowed.
        None values skips setting altogether (practical for inline comparison).
        """
        if sVal is None:
            return;
        assert isinstance(sVal, str);
        printVerbose(2, f"EnvManager: Setting {sKey}={sVal}");
        self.env[sKey] = sVal;

    def unset(self, sKey):
        """
        Unsets (deletes) a key from the set.
        """
        if sKey in self.env:
            del self.env[sKey];

    def append(self, sKey, sVal):
        """
        Appends a value to an existing key.
        If the key does not exist yet, it will be created.
        """
        return self.set(sKey, self.env[sKey] + sVal if sKey in self.env else sVal);

    def prependPath(self, sKey, sPath, enmBuildTarget = g_enmHostTarget):
        """
        Prepends a path to a given key.
        """
        if not sPath or len(sPath) == 0:
            return True;
        if sKey not in self.env:
            return self.set(sKey, sPath);
        sDelim = ';' if enmBuildTarget == BuildTarget.WINDOWS else ':';
        return self.set(sKey, sPath + sDelim + self.env[sKey]);

    def get(self, key, default=None):
        """
        Retrieves the value of an environment variable, or a default if not set (optional).
        """
        return self.env.get(key, default);

    def modify(self, sKey, func):
        """
        Modifies the value of an existing environment variable using a function.
        """
        if sKey in self.env:
            self.env[sKey] = str(func(self.env[sKey]));
        else:
            raise KeyError(f"{sKey} not set in environment");

    def updateFromArgs(self, oArgs):
        """
        Updates environment variable store using a Namespace object from argparse.
        Each argument becomes an environment variable, set only if its value is not None.
        """
        for sKey, aValue in vars(oArgs).items():
            if aValue:
                if sKey.startswith('config_'):
                    self.set(sKey, str(aValue));
                else:
                    idxSep =  sKey.find("=");
                    if not idxSep:
                        break;
                    sKeyNew   = sKey[:idxSep];
                    aValueNew = sKey[idxSep + 1:];
                    self.set(sKeyNew, str(aValueNew));

    def write_single(self, fh, sKey, sVal = None, sWhat = None):
        """
        Writes a single key=value pair to the given file handle.
        """
        if sVal:
            sVal = ''.join(c if c != '\\' else '/' for c in sVal); # Translate to UNIX paths (for kBuild).
        fh.write(f'{sWhat if sWhat else ''}{sKey}={sVal if sVal else self.env[sKey]}\n');

    def write_all(self, fh, sWhat = None, asPrefixInclude = None, asPrefixExclude = None):
        """
        Writes all stored environment variables as KEY=VALUE pairs to the given file handle.
        """
        for sKey, sVal in self.env.items():
            if asPrefixExclude and any(sKey.startswith(p) for p in asPrefixExclude):
                continue;
            if asPrefixInclude and not any(sKey.startswith(p) for p in asPrefixInclude):
                continue;
            if sVal: # Might be None.
                self.write_single(fh, sKey, sVal, sWhat);
        return True;

    def write_all_as_exports(self, fh, enmBuildTarget, asPrefixInclude = None, asPrefixExclude = None):
        """
        Writes all stored environment variables as (system-specific) export / set KEY=VALUE pairs
        to the given file handle.
        """
        sWhat = 'set ' if enmBuildTarget == BuildTarget.WINDOWS else 'export ';
        return self.write_all(fh, sWhat, asPrefixInclude, asPrefixExclude);

    def write(self, fh, sKey, sWhat = None):
        """
        Writes a single key.
        """
        if sKey in self.env:
            sVal = self.env[sKey];
            if sVal:
                self.write_single(fh, sKey, sVal, sWhat);
                return True;
        return False;

    def write_as_export(self, fh, sKey, enmBuildTarget):
        """
        Writes a single key as an export.
        """
        sWhat = 'set ' if enmBuildTarget == BuildTarget.WINDOWS else 'export ';
        return self.write(fh, sKey, sWhat);

    def transform(self, mapTransform):
        """
        Evaluates mapping expressions and updates the affected environment variables.
        """
        for exprCur in mapTransform:
            result = exprCur(self.env);
            if isinstance(result, dict):
                self.env.update(result);

    def __getitem__(self, sName):
        """
        Magic function to return an environment variable if found, None if not found.
        """
        return self.get(sName, None);

# Global instance of the environment manager.
# This hold the configuration we later serialize into files.
g_oEnv = EnvManager();

class SimpleTable:
    """
    A simple table for outputting aligned text.
    """
    def __init__(self, asHeaders):
        """
        Constructor.
        """
        self.asHeaders = asHeaders;
        self.aRows = [];
        self.sFmt = '';
        self.aiWidths = [];

    def addRow(self, asCells):
        """
        Adds a row to the table.
        """
        assert len(asCells) == len(self.asHeaders);
        #self.aRows.append(asCells);
        self.aRows.append(tuple(str(cell) for cell in asCells))

    def print(self):
        """
        Prints the table to the given file handle.
        """

        # Compute maximum width for each column.
        aRows = [self.asHeaders] + self.aRows;
        aColWidths = [max(len(str(row[i])) for row in aRows) for i in range(len(self.asHeaders))];
        sFmt = '  '.join('{{:<{}}}'.format(w) for w in aColWidths);

        print(sFmt.format(*self.asHeaders));
        print('-' * (sum(aColWidths) + 2*(len(self.asHeaders)-1)));
        for row in self.aRows:
            print(sFmt.format(*row));

def print_targets(aeTargets):
    """
    Returns the given build targets list as a string.
    """
    if len(aeTargets) == 1:
        return aeTargets[0];
    return ', '.join(aeTargets[:-1]) + ' and ' + aeTargets[-1]

def show_syntax_help():
    """
    Prints syntax help.
    """
    print("Supported libraries (with configure options):\n");

    for oLibCur in g_aoLibs:
        sDisable     = f"--disable-{oLibCur.sName}";
        sWith        = f"--with-{oLibCur.sName}-path=<path>";
        sOnlyTargets = f" (only on {print_targets(oLibCur.aeTargets)})" if oLibCur.aeTargets != [ BuildTarget.ANY ] else "";
        print(f"    {sDisable:<30}{sWith:<40}{sOnlyTargets}");

    print("\nSupported tools (with configure options):\n");

    for oToolCur in g_aoTools:
        sDisable     = f"--disable-{oToolCur.sName}";
        sOnlyTargets = f" (only on {print_targets(oToolCur.aeTargets)})" if oToolCur.aeTargets != [ BuildTarget.ANY ] else "";
        sWith        = f"--with-{oToolCur.sName}-path=<path>";
        print(f"    {sDisable:<30}{sWith:<40}{sOnlyTargets}");
    print(f"""
    --help                         Show this help message and exit

Examples:
    {g_sScriptName} --disable-libvpx
    {g_sScriptName} --with-libpng-path=/usr/local
    {g_sScriptName} --disable-yasm --disable-openwatcom
    {g_sScriptName} --disable-libstdc++
    {g_sScriptName} --disable-qt6

Hint: Combine any supported --disable-<lib|tool> and --with-<lib>-path=PATH options.
""");

g_aoLibs = sorted([
    LibraryCheck("softfloat", [ "softfloat.h", "iprt/cdefs.h" ], [ "libsoftfloat" ], [ BuildTarget.ANY ],
                 '#define IN_RING3\n#include <softfloat.h>\nint main() { softfloat_state_t s; float32_t x, y; f32_add(x, y, &s); printf("<found>"); return 0; }\n'),
    LibraryCheck("dxmt", [ "version.h" ], [ "libdxmt" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                '#include <version.h>\nint main() { return 0; }\n'),
    LibraryCheck("dxvk", [ "dxvk/dxvk.h" ], [ "libdxvk" ],  [ BuildTarget.LINUX ],
                 '#include <dxvk/dxvk.h>\nint main() { printf("<found>"); return 0; }\n'),
    LibraryCheck("libalsa", [ "alsa/asoundlib.h" ], [ "libasound" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <alsa/asoundlib.h>\n#include <alsa/version.h>\nint main() { snd_pcm_info_sizeof(); printf("%s", SND_LIB_VERSION_STR); return 0; }\n'),
    LibraryCheck("libcap", [ "sys/capability.h" ], [ "libcap" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <sys/capability.h>\nint main() { cap_t c = cap_init(); printf("<found>"); return 0; }\n'),
    LibraryCheck("libcursor", [ "X11/cursorfont.h" ], [ "libXcursor" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <X11/Xcursor/Xcursor.h>\nint main() { printf("%d.%d", XCURSOR_LIB_MAJOR, XCURSOR_LIB_MINOR); return 0; }\n'),
    LibraryCheck("curl", [ "curl/curl.h" ], [ "libcurl" ], [ BuildTarget.ANY ],
                 '#include <curl/curl.h>\nint main() { printf("%s", LIBCURL_VERSION); return 0; }\n'),
    LibraryCheck("libdevmapper", [ "libdevmapper.h" ], [ "libdevmapper" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <libdevmapper.h>\nint main() { char v[64]; dm_get_library_version(v, sizeof(v)); printf("%s", v); return 0; }\n'),
    LibraryCheck("libjpeg-turbo", [ "turbojpeg.h" ], [ "libturbojpeg" ], [ BuildTarget.ANY ],
                 '#include <turbojpeg.h>\nint main() { tjInitCompress(); printf("<found>"); return 0; }\n'),
    LibraryCheck("liblzf", [ "lzf.h" ], [ "liblzf" ], [ BuildTarget.ANY ],
                 '#include <liblzf/lzf.h>\nint main() { printf("%d.%d", LZF_VERSION >> 8, LZF_VERSION & 0xff);\n#if LZF_VERSION >= 0x0105\nreturn 0;\n#else\nreturn 1;\n#endif\n }\n'),
    LibraryCheck("liblzma", [ "lzma.h" ], [ "liblzma" ], [ BuildTarget.ANY ],
                 '#include <lzma.h>\nint main() { printf("%s", lzma_version_string()); return 0; }\n'),
    LibraryCheck("libogg", [ "ogg/ogg.h" ], [ "libogg" ], [ BuildTarget.ANY ],
                 '#include <ogg/ogg.h>\nint main() { oggpack_buffer o; oggpack_get_buffer(&o); printf("<found>"); return 0; }\n'),
    LibraryCheck("libpam", [ "security/pam_appl.h" ], [ "libpam" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <security/pam_appl.h>\nint main() { \n#ifdef __LINUX_PAM__\nprintf("%d.%d", __LINUX_PAM__, __LINUX_PAM_MINOR__); if (__LINUX_PAM__ >= 1) return 0;\n#endif\nreturn 1; }\n'),
    LibraryCheck("libpng", [ "png.h" ], [ "libpng" ], [ BuildTarget.ANY ],
                 '#include <png.h>\nint main() { printf("%s", PNG_LIBPNG_VER_STRING); return 0; }\n'),
    LibraryCheck("libpthread", [ "pthread.h" ], [ "libpthread" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <unistd.h>\n#include <pthread.h>\nint main() { \n#ifdef _POSIX_VERSION\nprintf("%d", (long)_POSIX_VERSION); return 0;\n#else\nreturn 1;\n#endif\n }\n'),
    LibraryCheck("libpulse", [ "pulse/pulseaudio.h", "pulse/version.h" ], [ "libpulse" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <pulse/version.h>\nint main() { printf("%s", pa_get_library_version()); return 0; }\n'),
    LibraryCheck("libslirp", [ "slirp/libslirp.h", "slirp/libslirp-version.h" ], [ "libslirp" ], [ BuildTarget.ANY ],
                 '#include <slirp/libslirp.h>\n#include <slirp/libslirp-version.h>\nint main() { printf("%d.%d.%d", SLIRP_MAJOR_VERSION, SLIRP_MINOR_VERSION, SLIRP_MICRO_VERSION); return 0; }\n'),
    LibraryCheck("libssh", [ "libssh/libssh.h" ], [ "libssh" ], [ BuildTarget.ANY ],
                 '#include <libssh/libssh.h>\n#include <libssh/libssh_version.h>\nint main() { printf("%d.%d.%d", LIBSSH_VERSION_MAJOR, LIBSSH_VERSION_MINOR, LIBSSH_VERSION_MICRO); return 0; }\n'),
    LibraryCheck("libstdc++", [ "c++/11/iostream" ], [ ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 "int main() { \n #ifdef __GLIBCXX__\nstd::cout << __GLIBCXX__;\n#elif defined(__GLIBCPP__)\nstd::cout << __GLIBCPP__;\n#else\nreturn 1\n#endif\nreturn 0; }\n",
                 asAltIncFiles = [ "c++/4.8.2/iostream", "c++/iostream" ]),
    LibraryCheck("libtpms", [ "libtpms/tpm_library.h" ], [ "libtpms" ], [ BuildTarget.ANY ],
                 '#include <libtpms/tpm_library.h>\nint main() { printf("%d.%d.%d", TPM_LIBRARY_VER_MAJOR, TPM_LIBRARY_VER_MINOR, TPM_LIBRARY_VER_MICRO); return 0; }\n'),
    LibraryCheck("libvncserver", [ "rfb/rfb.h", "rfb/rfbclient.h" ], [ "libvncserver" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <rfb/rfb.h>\nint main() { printf("%s", LIBVNCSERVER_PACKAGE_VERSION); return 0; }\n'),
    LibraryCheck("libvorbis", [ "vorbis/vorbisenc.h" ], [ "libvorbis", "libvorbisenc" ], [ BuildTarget.ANY ],
                 '#include <vorbis/vorbisenc.h>\nint main() { vorbis_info v; vorbis_info_init(&v); int vorbis_rc = vorbis_encode_init_vbr(&v, 2 /* channels */, 44100 /* hz */, (float).4 /* quality */); printf("<found>"); return 0; }\n'),
    LibraryCheck("libvpx", [ "vpx/vpx_decoder.h" ], [ "libvpx" ], [ BuildTarget.ANY ],
                 '#include <vpx/vpx_codec.h>\nint main() { printf("%s", vpx_codec_version_str()); return 0; }\n'),
    LibraryCheck("libxml2", [ "libxml/parser.h" ] , [ "libxml2" ], [ BuildTarget.ANY ],
                 '#include <libxml/xmlversion.h>\nint main() { printf("%s", LIBXML_DOTTED_VERSION); return 0; }\n'),
    LibraryCheck("zlib", [ "zlib.h" ], [ "libz" ], [ BuildTarget.ANY ],
                 '#include <zlib.h>\nint main() { printf("%s", ZLIB_VERSION); return 0; }\n'),
    LibraryCheck("lwip", [ "lwip/init.h" ], [ "liblwip" ], [ BuildTarget.ANY ],
                 '#include <lwip/init.h>\nint main() { printf("%d.%d.%d", LWIP_VERSION_MAJOR, LWIP_VERSION_MINOR, LWIP_VERSION_REVISION); return 0; }\n'),
    LibraryCheck("opengl", [ "GL/gl.h" ], [ "libGL" ], [ BuildTarget.ANY ],
                 '#include <GL/gl.h>\n#include <stdio.h>\nint main() { const GLubyte *s = glGetString(GL_VERSION); printf("%s", s ? (const char *)s : "<found>"); return 0; }\n'),
    LibraryCheck("qt6", [ "QtCore/qconfig.h" ], [ "libQt6Core" ], [ BuildTarget.ANY ],
                 '#include <stdio.h>\n#include <qt6/QtCore/qconfig.h>\nint main() { printf("%s", QT_VERSION_STR); }',
                 asAltIncFiles = [ "qt/QtCore/qglobal.h", "QtCore/qcoreapplication.h", "qt6/QtCore/qcoreapplication.h" ] ),
    LibraryCheck("sdl2", [ "SDL2/SDL.h" ], [ "libSDL2" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <SDL2/SDL.h>\nint main() { printf("%d.%d.%d", SDL_MAJOR_VERSION, SDL_MINOR_VERSION, SDL_PATCHLEVEL); return 0; }\n',
                 asAltIncFiles = [ "SDL.h" ]),
    LibraryCheck("sdl2_ttf", [ "SDL2/SDL_ttf.h" ], [ "libSDL2_ttf" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <SDL2/SDL_ttf.h>\nint main() { printf("%d.%d.%d", SDL_TTF_MAJOR_VERSION, SDL_TTF_MINOR_VERSION, SDL_TTF_PATCHLEVEL); return 0; }\n',
                 asAltIncFiles = [ "SDL_ttf.h" ]),
    LibraryCheck("x11", [ "X11/Xlib.h" ], [ "libX11" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <X11/Xlib.h>\nint main() { XOpenDisplay(NULL); printf("<found>"); return 0; }\n'),
    LibraryCheck("xext", [ "X11/extensions/Xext.h" ], [ "libXext" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <X11/Xlib.h>\n#include <X11/extensions/Xext.h>\nint main() { XSetExtensionErrorHandler(NULL); printf("<found>"); return 0; }\n'),
    LibraryCheck("xmu", [ "X11/Xmu/Xmu.h" ], [ "libXmu" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <X11/Xmu/Xmu.h>\nint main() { XmuMakeAtom("test"); printf("<found>"); return 0; }\n', aeTargetsExcluded=[ BuildTarget.DARWIN ]),
    LibraryCheck("xrandr", [ "X11/extensions/Xrandr.h" ], [ "libXrandr", "libX11" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <X11/Xlib.h>\n#include <X11/extensions/Xrandr.h>\nint main() { Display *dpy = XOpenDisplay(NULL); Window root = RootWindow(dpy, 0); XRRScreenConfiguration *c = XRRGetScreenInfo(dpy, root); printf("<found>"); return 0; }\n'),
    LibraryCheck("libxinerama", [ "X11/extensions/Xinerama.h" ], [ "libXinerama", "libX11" ], [ BuildTarget.LINUX, BuildTarget.SOLARIS, BuildTarget.BSD ],
                 '#include <X11/Xlib.h>\n#include <X11/extensions/Xinerama.h>\nint main() { Display *dpy = XOpenDisplay(NULL); XineramaIsActive(dpy); printf("<found>"); return 0; }\n')
], key=lambda l: l.sName);

# Note: The order is important here for subsequent checks.
#       Don't change without proper testing!
g_aoTools = [
    ToolCheck("gcc", asCmd = [ "gcc" ], fnCallback = ToolCheck.checkCallback_gcc, aeTargets = [ BuildTarget.LINUX, BuildTarget.SOLARIS ] ),
    ToolCheck("visualcpp", asCmd = [ ], fnCallback = ToolCheck.checkCallback_VisualCPP, aeTargets = [ BuildTarget.WINDOWS ] ),
    ToolCheck("win10sdk", asCmd = [ ], fnCallback = ToolCheck.checkCallback_Win10SDK, aeTargets = [ BuildTarget.WINDOWS ] ),
    ToolCheck("winddk", asCmd = [ ], fnCallback = ToolCheck.checkCallback_WinDDK, aeTargets = [ BuildTarget.WINDOWS ] ),
    ToolCheck("devtools", asCmd = [ ], fnCallback = ToolCheck.checkCallback_devtools ),
    ToolCheck("gsoap", asCmd = [ ], fnCallback = ToolCheck.checkCallback_GSOAP),
    ToolCheck("java", asCmd = [ "java" ]),
    ToolCheck("kbuild", asCmd = [ "kbuild" ], fnCallback = ToolCheck.checkCallback_kBuild ),
    ToolCheck("makeself", asCmd = [ "makeself" ], aeTargets = [ BuildTarget.LINUX ]),
    ToolCheck("openwatcom", asCmd = [ "wcl", "wcl386", "wlink" ], fnCallback = ToolCheck.checkCallback_OpenWatcom ),
    ToolCheck("python_c_api", asCmd = [ ], fnCallback = ToolCheck.checkCallback_PythonC_API ),
    ToolCheck("python_modules", asCmd = [ ], fnCallback = ToolCheck.checkCallback_PythonModules ),
    ToolCheck("xcode", asCmd = [], fnCallback = ToolCheck.checkCallback_XCode, aeTargets = [ BuildTarget.DARWIN ]),
    ToolCheck("yasm", asCmd = [ 'yasm' ], aeTargets = [ BuildTarget.ANY ]),
];

def write_autoconfig_kmk(sFilePath, enmBuildTarget, oEnv, aoLibs, aoTools):
    """
    Writes the AutoConfig.kmk file with SDK paths and enable/disable flags.
    Each library/tool gets VBOX_WITH_<NAME>, SDK_<NAME>_LIBS, SDK_<NAME>_INCS.
    """

    _ = enmBuildTarget, aoTools; # Unused for now.

    try:
        with open(sFilePath, "w", encoding = "utf-8") as fh:
            fh.write(f"""
# -*- Makefile -*-
#
# Automatically generated by
#
#   {g_sScriptName} """ + ' '.join(sys.argv[1:]) + f"""
#
# DO NOT EDIT THIS FILE MANUALLY
# It will be completely overwritten if {g_sScriptName} is executed again.
#
# Generated on """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """
#
\n""");
            oEnv.write_all(fh, asPrefixInclude = ['VBOX_', 'PATH_TOOL_' ]);
            fh.write('\n');

            for oLibCur in aoLibs:
                sVarBase = oLibCur.sName.upper().replace("+", "PLUS").replace("-", "_");
                sEnabled = '1' if oLibCur.fHave else '';
                fh.write(f"VBOX_WITH_{sVarBase}={sEnabled}\n");
                if oLibCur.fHave and (oLibCur.asLibPaths or oLibCur.asIncPaths):
                    if oLibCur.asLibPaths:
                        g_oEnv.write_single(fh, f'SDK_{sVarBase}_LIBS', oLibCur.asLibPaths[0]);
                    if oLibCur.asIncPaths:
                        g_oEnv.write_single(fh, f'SDK_{sVarBase}_INCS', oLibCur.asIncPaths[0]);

            g_oEnv.write_single(fh, 'PATH_SDK_WINSDK10');
            g_oEnv.write_single(fh, 'SDK_WINSDK10_VERSION');

        return True;
    except OSError as ex:
        printError(f"Failed to write AutoConfig.kmk to {sFilePath}: {str(ex)}");
    return False;

def write_env(sFilePath, enmBuildTarget, enmBuildArch, oEnv, aoLibs, aoTools):
    """
    Writes the env.sh file with kBuild configuration and other tools stuff.
    """

    _ = aoLibs, aoTools; # Unused for now.

    try:
        with open(sFilePath, "w", encoding = "utf-8") as fh:
            sTimestamp  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S");
            sScriptArgs = ' '.join(sys.argv[1:]);
            if g_enmHostTarget != BuildTarget.WINDOWS:
                fh.write(f"""
#!/bin/bash
# -*- Environment -*-
#
# Automatically generated by
#
#   {g_sScriptName} """ + sScriptArgs + f"""
#
# DO NOT EDIT THIS FILE MANUALLY
# It will be completely overwritten if {g_sScriptName} is executed again.
#
# Generated on """ + sTimestamp + """
#\n""");
            else: # non-Windows.
                fh.write(f"""
@echo off
rem -*- Environment -*-
rem
rem Automatically generated by
rem
rem   {g_sScriptName} """ + sScriptArgs + f"""
rem
rem DO NOT EDIT THIS FILE MANUALLY
rem It will be completely overwritten if {g_sScriptName} is executed again.
rem
rem Generated on """ +  sTimestamp + """
rem\n""");
            oEnv.write_all_as_exports(fh, enmBuildTarget, asPrefixInclude = [ 'KBUILD_' ]);
            sPath = oEnv['PATH_OUT_BASE'];
            if sPath:
                fh.write(f'PATH_OUT_BASE={sPath}\n');
                fh.write( 'set PATH_OUT_BASE\n');

            oEnv.prependPath('PATH', os.path.join(g_sScriptPath, g_oEnv['KBUILD_PATH'], 'bin', f'{enmBuildTarget}.{enmBuildArch}'));
            oEnv.write_as_export(fh, 'PATH', enmBuildTarget);

        return True;
    except OSError as ex:
        printError(f"Failed to write environment file to {sFilePath}: {str(ex)}");
    return False;

def main():
    """
    Main entry point.
    """
    global g_cVerbosity;
    global g_fDebug;
    global g_fContOnErr;
    global g_sFileLog;
    global g_sDevBinPath;

    #
    # argparse config namespace rules:
    # - Everything internally used is prefixed with 'config_'.
    # - Library options are prefixed with 'config_libs_'.
    # - Tool options are prefixed with 'config_tools_'.
    # - VirtualBox-specific environment variables (VBOX_WITH_, VBOX_ONLY_ and so on) are written as-is but lowercase (e.g. 'vbox_with_docs=1'),
    #   including the value to be set.
    #
    oParser = argparse.ArgumentParser(description='Checks and configures the build environment', add_help=False);
    oParser.add_argument('-h', '--help', help="Displays this help", action='store_true');
    oParser.add_argument('-v', '--verbose', help="Enables verbose output", action='count', default=0, dest='config_verbose');
    oParser.add_argument('-V', '--version', help="Prints the version of this script", action='store_true');
    for oLibCur in g_aoLibs:
        oParser.add_argument(f'--disable-{oLibCur.sName}', action='store_true', default=None, dest=f'config_libs_disable_{oLibCur.sName}');
        oParser.add_argument(f'--with-{oLibCur.sName}-path', dest=f'config_libs_path_{oLibCur.sName}');
        # For debugging / development only. We don't expose this in the syntax help.
        oParser.add_argument(f'--only-{oLibCur.sName}', action='store_true', default=None, dest=f'config_libs_only_{oLibCur.sName}');
    for oToolCur in g_aoTools:
        oParser.add_argument(f'--disable-{oToolCur.sName}', action='store_true', default=None, dest=f'config_tools_disable_{oToolCur.sName}');
        oParser.add_argument(f'--with-{oToolCur.sName}-path', dest=f'config_tools_path_{oToolCur.sName}');
        # For debugging / development only. We don't expose this in the syntax help.
        oParser.add_argument(f'--only-{oToolCur.sName}', action='store_true', default=None, dest=f'config_tools_only_{oToolCur.sName}');

    oParser.add_argument('--disable-docs', help='Disables building the documentation', action='store_true', default=None, dest='VBOX_WITH_DOCS=');
    oParser.add_argument('--disable-python', help='Disables building the Python bindings', action='store_true', default=None, dest='VBOX_WITH_PYTHON=');
    oParser.add_argument('--disable-pylint', help='Disables using pylint', action='store_true', default=None, dest='VBOX_WITH_PYLINT=');
    oParser.add_argument('--disable-sdl', help='Disables building the SDL frontend', action='store_true', default=None, dest='VBOX_WITH_SDL=');
    oParser.add_argument('--disable-udptunnel', help='Disables building UDP tunnel support', action='store_true', default=None, dest='VBOX_WITH_UDPTUNNEL=');
    oParser.add_argument('--with-hardening', help='Enables or disables hardening', action='store_true', default=None, dest='VBOX_WITH_HARDENING=1');
    oParser.add_argument('--without-hardening', help='Enables or disables hardening', action='store_true', default=None, dest='VBOX_WITH_HARDENing=');
    oParser.add_argument('--file-autoconfig', help='Path to output AutoConfig.kmk file', action='store_true', default='AutoConfig.kmk', dest='config_file_autoconfig');
    oParser.add_argument('--file-env', help='Path to output env[.bat|.sh] file', action='store_true', \
                         default='env.bat' if g_enmHostTarget == BuildTarget.WINDOWS else 'env.sh', dest='config_file_env');
    oParser.add_argument('--file-log', help='Path to output log file', action='store_true', default='configure.log', dest='config_file_log');
    oParser.add_argument('--only-additions', help='Only build Guest Additions related libraries and tools', action='store_true', default=None, dest='VBOX_ONLY_ADDITIONS=');
    oParser.add_argument('--only-docs', help='Only build the documentation', action='store_true', default=None, dest='VBOX_ONLY_DOCS=1');
    oParser.add_argument('--path-out-base', help='Specifies the output directory', action='store', default=None, dest='config_path_out_base');
    oParser.add_argument('--ose', help='Builds the OSE version', action='store_true', default=None, dest='VBOX_OSE=1');
    oParser.add_argument('--debug', help='Runs in debug mode. Only use for development', action='store_true', default=False, dest='config_debug');
    oParser.add_argument('--nofatal', '--continue-on-error', help='Continues execution on fatal errors', action='store_true', dest='config_nofatal');
    oParser.add_argument('--build-profile', help='Build with a profiling support', action='store_true', default=None, dest='KBUILD_TYPE=profile');
    oParser.add_argument('--build-target', help='Specifies the build target', action='store_true', default=None, dest='config_build_target');
    oParser.add_argument('--build-arch', help='Specifies the build architecture', action='store_true', default=None, dest='config_build_arch');
    oParser.add_argument('--build-debug', help='Build with debugging symbols and assertions', action='store_true', default=None, dest='KBUILD_TYPE=debug');
    oParser.add_argument('--build-headless', help='Build headless (without any GUI frontend)', action='store_true', dest='config_build_headless');
    oParser.add_argument('--internal-first', help='Check internal tools (tools/win.*) first (default)', action='store_true', dest='config_internal_first');
    oParser.add_argument('--internal-last', help='Check internal tools (tools/win.*) last', action='store_true', dest='config_internal_last');
    oParser.add_argument('--append-ewdk-path', '--append-ewdk-dir', help='Adds an EWDK drive to search.', dest='config_path_append_ewdk');
    oParser.add_argument('--prepend-ewdk-path', '--prepend-ewdk-dir', help='Adds an EWDK drive to search.', dest='config_path_prepend_ewdk');
    oParser.add_argument('--append-programfiles-path', '--append-programfiles-dir', help='Adds an alternative Program Files directory to search.', dest='config_path_append_programfiles');
    oParser.add_argument('--prepend-programfiles-path', '--prepend-programfiles-dir', help='Adds an alternative Program Files directory to search.', dest='config_path_prepend_programfiles');
    oParser.add_argument('--append-tools-path', '--append-tools-dir', help='Adds an alternative tools directory to search.', dest='config_path_append_tools');
    oParser.add_argument('--prepend-tools-path', '--prepend-tools-dir', help='Adds an alternative tools directory to search.', dest='config_path_prepend_tools');
    # Windows-specific arguments (the second arguments points to legacy versions kept for backwards compatibility).
    oParser.add_argument('--disable-com', '--disable-com', help='Disable building components which require COM', action='store_true', dest='config_disable_com');
    oParser.add_argument('--with-win-ddk', '--with-DDK', help='Where the WDK is to be found', action='store_true', dest='config_win_ddk_path');
    oParser.add_argument('--with-win-midl', '--with-midl', help='Where midl.exe is to be found', action='store_true', dest='config_win_midl_path');
    oParser.add_argument('--with-win-nasm', '--with-nasm', help='Where NASM is to be found (optional)', action='store_true', dest='config_win_nasm_path');
    oParser.add_argument('--with-win-sdk', '--with-SDK', help='Where the Windows SDK is to be found', action='store_true', dest='config_win_sdk_path');
    oParser.add_argument('--with-win-sdk10', '--with-SDK10', help='Where the Windows 10 SDK/WDK is to be found', action='store_true', dest='config_win_sdk10_path');
    oParser.add_argument('--with-win-vc-common', '--with-VC-Common', help='Maybe needed for 2015 and older to locate the Common7 directory', action='store_true', dest='config_win_vc_common_path');
    oParser.add_argument('--with-win-vc', '--with-VC', help='Where the Visual C++ compiler is to be found. Expecting bin, include and lib subdirs', action='store_true', dest='config_win_vc_path');
    oParser.add_argument('--with-win-vcpkg-root', help='Where the VCPKG root directory to be found', action='store_true', dest='config_win_vcpkg_root');
    oParser.add_argument('--with-win-yasm', '--with-yasm', help='Where YASM is to be found', action='store_true', dest='config_libs_path_yasm'); ## Note: Same as above in libs block.

    try:
        oArgs = oParser.parse_args();
    except SystemExit:
        print('Invalid argument(s) -- try --help for more information.');
        return 2;

    if oArgs.help:
        show_syntax_help();
        return 2;
    if oArgs.version:
        print('1.0'); ## @todo Return SVN rev.
        return 0;

    logf = open(g_sFileLog, "w", encoding="utf-8");
    sys.stdout = Log(sys.stdout, logf);
    sys.stderr = Log(sys.stderr, logf);

    g_cVerbosity = oArgs.config_verbose;
    g_fDebug = oArgs.config_debug;
    g_fContOnErr = oArgs.config_nofatal;
    g_sFileLog = oArgs.config_file_log;
    g_sDevBinPath = os.path.join(g_sDevPath, f'{g_enmHostTarget}.{g_enmHostArch}');

    # Set defaults.
    g_oEnv.set('KBUILD_HOST', g_enmHostTarget);
    g_oEnv.set('KBUILD_HOST_ARCH', g_enmHostArch);
    g_oEnv.set('KBUILD_TYPE', BuildType.RELEASE);
    g_oEnv.set('KBUILD_TARGET', oArgs.config_build_target if oArgs.config_build_target else g_enmHostTarget);
    g_oEnv.set('KBUILD_TARGET_ARCH', oArgs.config_build_arch if oArgs.config_build_arch else g_enmHostArch);
    g_oEnv.set('KBUILD_TARGET_CPU', 'blend'); ## @todo Check this.
    g_oEnv.set('KBUILD_PATH', oArgs.config_tools_path_kbuild);
    g_oEnv.set('VBOX_WITH_HARDENING', '1');
    g_oEnv.set('PATH_OUT_BASE', oArgs.config_path_out_base);

    # Handle prepending / appending certain paths ('--[prepend|append]-<whatever>-path') arguments.
    for sArgCur, _ in g_asPathsPrepend.items(): # ASSUMES that g_asPathsAppend and g_asPathsPrepend are in sync.
        sPath = getattr(oArgs, f'config_path_append_{sArgCur}');
        if sPath:
            g_asPathsAppend[ sArgCur ].extend( [ sPath ] );
        sPath = getattr(oArgs, f'config_path_prepend_{sArgCur}');
        if sPath:
            g_asPathsPrepend[ sArgCur ].extend( [ sPath ] );

    # Apply updates from command line arguments.
    g_oEnv.updateFromArgs(oArgs);

    # Filter libs and tools based on --only-XXX flags.
    aoOnlyLibs = [lib for lib in g_aoLibs if getattr(oArgs, f'config_libs_only_{lib.sName}', False)];
    aoOnlyTools = [tool for tool in g_aoTools if getattr(oArgs, f'config_tools_only_{tool.sName}', False)];
    aoLibsToCheck = aoOnlyLibs if aoOnlyLibs else g_aoLibs;
    aoToolsToCheck = aoOnlyTools if aoOnlyTools else g_aoTools;
    # Filter libs and tools based on build target.
    aoLibsToCheck  = [lib for lib in aoLibsToCheck if g_oEnv['KBUILD_TARGET'] in lib.aeTargets or BuildTarget.ANY in lib.aeTargets];
    aoToolsToCheck = [tool for tool in aoToolsToCheck if g_oEnv['KBUILD_TARGET'] in tool.aeTargets or BuildTarget.ANY in tool.aeTargets];

    print( 'VirtualBox configuration script');
    print();
    print(f'Running on {platform.system()} {platform.release()} ({platform.machine()})');
    print(f'Using Python {sys.version}');
    print();
    print(f'Host OS / arch     : { g_sHostTarget}.{g_sHostArch}');
    print(f'Building for target: { g_oEnv["KBUILD_TARGET"] }.{ g_oEnv["KBUILD_TARGET_ARCH"] }');
    print(f'Build type         : { g_oEnv["KBUILD_TYPE"] }');
    print();

    #
    # Handle OSE building.
    #
    fOSE = True if g_oEnv.get('VBOX_OSE') == '1' else None;
    if  not fOSE  \
    and os.path.exists('src/VBox/ExtPacks/Puel/ExtPack.xml'):
        print('Found ExtPack, assuming to build PUEL version');
        g_oEnv.set('VBOX_OSE', '1');
    print('Building %s version' % ('OSE' if (fOSE is None or fOSE is True) else 'PUEL'));
    print();

    #
    # Handle environment variable transformations.
    #
    # This is needed to set/unset/change other environment variables on already set ones.
    # For instance, building OSE requires certain components to be disabled. Same when a certain library gets disabled.
    #
    envTransforms = [
        # Disabling building the docs when only building Additions or explicitly disabled building the docs.
        lambda env: { 'VBOX_WITH_DOCS_PACKING': ''} if g_oEnv['VBOX_ONLY_ADDITIONS'] or g_oEnv['VBOX_WITH_DOCS'] == '' else {},
        # Disable building the ExtPack VNC when only building Additions or OSE.
        lambda env: { 'VBOX_WITH_EXTPACK_VNC': '' } if g_oEnv['VBOX_ONLY_ADDITIONS'] or g_oEnv['VBOX_OSE'] == '1' else {},
        lambda env: { 'VBOX_WITH_WEBSERVICES': '' } if g_oEnv['VBOX_ONLY_ADDITIONS'] else {},
        # Disable stuff which aren't available in OSE.
        lambda env: { 'VBOX_WITH_VALIDATIONKIT': '' , 'VBOX_WITH_WIN32_ADDITIONS': '' } if g_oEnv['VBOX_OSE'] else {},
        lambda env: { 'VBOX_WITH_EXTPACK_PUEL_BUILD': '' } if g_oEnv['VBOX_ONLY_ADDITIONS'] else {},
        lambda env: { 'VBOX_WITH_QTGUI': '' } if g_oEnv['CONFIG_LIBS_DISABLE_QT'] else {},
        # Disable components if we want to build headless.
        lambda env: { 'VBOX_WITH_HEADLESS': '1', \
                      'VBOX_WITH_QTGUI': '', \
                      'VBOX_WITH_SECURELABEL': '', \
                      'VBOX_WITH_VMSVGA3D': '', \
                      'VBOX_WITH_3D_ACCELERATION' : '', \
                      'VBOX_GUI_USE_QGL' : '' } if g_oEnv['CONFIG_BUILD_HEADLESS'] else {},
        # Disable recording if libvpx is disabled.
        lambda env: { 'VBOX_WITH_LIBVPX': '', \
                      'VBOX_WITH_RECORDING': '' } if g_oEnv['CONFIG_LIBS_DISABLE_LIBVPX'] else {},
        # Disable audio recording if libvpx is disabled.
        lambda env: { 'VBOX_WITH_LIBOGG': '', \
                      'VBOX_WITH_LIBVORBIS': '', \
                      'VBOX_WITH_AUDIO_RECORDING': '' } if  g_oEnv['CONFIG_LIBS_DISABLE_LIBOGG'] \
                                                        and g_oEnv['CONFIG_LIBS_DISABLE_LIBVORBIS'] else {},
        # Disable building webservices if GSOAP is disabled.
        lambda env: { 'VBOX_WITH_GSOAP': '', \
                      'VBOX_WITH_WEBSERVICES': '' } if g_oEnv['CONFIG_TOOLS_DISABLE_GSOAP'] else {},
        # Disable components which require COM.
        lambda env: { 'VBOX_WITH_MAIN': '', \
                      'VBOX_WITH_QTGUI': '', \
                      'VBOX_WITH_VBOXSDL': '', \
                      'VBOX_WITH_DEBUGGER_GUI': '' } if g_oEnv['CONFIG_DISABLE_COM'] else {},
    ];
    g_oEnv.transform(envTransforms);

    if g_cVerbosity >= 2:
        printVerbose(2, 'Environment manager variables:');
        print(g_oEnv.env);

    #
    # Perform OS tool checks.
    # These are essential and must be present for all following checks.
    # Sorted by importance.
    #
    aOsTools = {
        BuildTarget.LINUX:   [ 'pkg-config', 'gcc', 'make',  ],
        BuildTarget.DARWIN:  [ 'clang', 'make', 'brew' ],
        BuildTarget.WINDOWS: [ ], # Done via own callbacks in the ToolCheck class down below.
        BuildTarget.SOLARIS: [ 'pkg-config', 'cc', 'gmake' ]
    };
    aOsToolsToCheck = aOsTools.get( g_oEnv[ 'KBUILD_TARGET' ], [] );
    oOsToolsTable = SimpleTable([ 'Tool', 'Status', 'Version', 'Path' ]);
    for sBinary in aOsToolsToCheck:
        sCmdPath, sVer = checkWhich(sBinary, sBinary);
        oOsToolsTable.addRow(( sBinary,
                               'ok' if sCmdPath else 'failed',
                               sVer if sVer else "-",
                               "-" ));
    oOsToolsTable.print();

    #
    # Perform tool checks.
    #
    if g_cErrors == 0 \
    or g_fContOnErr:
        print();
        for oToolCur in aoToolsToCheck:
            oToolCur.setArgs(oArgs);
            if  not oToolCur.performCheck() \
            and not g_fContOnErr:
                break;

    #
    # Perform library checks.
    #
    if g_cErrors == 0 \
    or g_fContOnErr:
        print();
        for oLibCur in aoLibsToCheck:
            oLibCur.setArgs(oArgs);
            if  not oLibCur.performCheck() \
            and not g_fContOnErr:
                break;
    #
    # Print summary.
    #
    oToolsTable = SimpleTable([ 'Tool', 'Status', 'Version', 'Path' ]);
    for oToolCur in aoToolsToCheck:
        oToolsTable.addRow(( oToolCur.sName,
                                oToolCur.getStatusString().split()[0],
                                oToolCur.sVer if oToolCur.sVer else '-',
                                oToolCur.sCmdPath if oToolCur.sCmdPath else '-' ));
    print();
    oToolsTable.print();
    print();

    oLibsTable = SimpleTable([ 'Library', 'Status', 'Version', 'Include Path(s)' ]);
    for oLibCur in aoLibsToCheck:
        oLibsTable.addRow(( oLibCur.sName,
                            oLibCur.getStatusString().split()[0],
                            oLibCur.sVer if oLibCur.sVer else '-',
                            oLibCur.asIncPaths[0] if oLibCur.asIncPaths else '-' ));
        if oLibCur.asIncPaths and len(oLibCur.asIncPaths) > 1:
            for sIncPath in oLibCur.asIncPaths[1:]:
                oLibsTable.addRow(( ' ', ' ', ' ', sIncPath));

    print();
    oLibsTable.print();
    print();

    if g_cErrors == 0 \
    or g_fContOnErr:
        if write_autoconfig_kmk(oArgs.config_file_autoconfig, g_enmHostTarget, g_oEnv, g_aoLibs, g_aoTools):
            if write_env(oArgs.config_file_env, g_enmHostTarget, g_enmHostArch, g_oEnv, g_aoLibs, g_aoTools):
                print();
                print(f'Successfully generated \"{oArgs.config_file_autoconfig}\" and \"{oArgs.config_file_env}\".');
                print();
                if g_enmHostTarget == BuildTarget.WINDOWS:
                    print();
                    print('Execute env.bat once before you start to build VirtualBox:');
                    print();
                    print('  env.bat');
                else:
                    print(f'Source {oArgs.config_file_env} once before you start to build VirtualBox:');
                    print();
                    print(f'  source "{oArgs.config_file_env}"');

                print();
                print( 'Then run the build with:');
                print( '  kmk');
                print();

        if g_enmHostTarget == BuildTarget.LINUX:
            print('To compile the kernel modules, do:');
            print();
            print(f"  cd {g_sOutPath}/{ g_oEnv['KBUILD_TARGET'] }.{ g_oEnv['KBUILD_TARGET_ARCH'] }/{ g_oEnv['KBUILD_TYPE'] }/bin/src");
            print('  make');
            print();

        if g_oEnv['VBOX_ONLY_ADDITIONS']:
            print();
            print('Tree configured to build only the Guest Additions');
            print();

        if g_oEnv['VBOX_WITH_HARDENING'] \
        or g_oEnv['VBOX_WITHOUT_HARDENING'] == '':
            print();
            print('  +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++');
            print('  Hardening is enabled which means that the VBox binaries will not run from');
            print('  the binary directory. The binaries have to be installed suid root and some');
            print('  more prerequisites have to be fulfilled which is normally done by installing');
            print('  the final package. For development, the hardening feature can be disabled');
            print('  by specifying the --disable-hardening parameter. Please never disable that');
            print('  feature for the final distribution!');
            print('  +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++');
            print();
        else:
            print();
            print('  +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++');
            print('  Hardening is disabled. Please do NOT build packages for distribution with');
            print('  disabled hardening!');
            print('  +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++ WARNING +++');
            print();

    if g_cWarnings:
        print(f'\nConfiguration completed with {g_cWarnings} warning(s). See {g_sFileLog} for details.');
        print('');
    if g_cErrors:
        print(f'\nConfiguration failed with {g_cErrors} error(s). See {g_sFileLog} for details.');
        print('');
    if  g_fContOnErr \
    and g_cErrors:
        print('\nWARNING: Errors occurred but non-fatal mode active -- check build carefully!');
        print('');

    if g_cErrors == 0:
        print('Enjoy!');

    print('\nWork in progress! Do not use for production builds yet!\n');

    logf.close();
    return 0 if g_cErrors == 0 else 1;

if __name__ == "__main__":
    sys.exit(main());
