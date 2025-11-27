#!/usr/bin/env python3

# -*- coding: utf-8 -*-
# $Id: configure.py 111931 2025-11-27 17:04:48Z andreas.loeffler@oracle.com $
# pylint: disable=global-statement
# pylint: disable=line-too-long
# pylint: disable=too-many-lines
# pylint: disable=unnecessary-semicolon
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
import datetime
import glob
import io
import os
import platform
import shutil
import subprocess
import sys
import tempfile

g_sScriptPath = os.path.abspath(os.path.dirname(__file__));
g_sScriptName = os.path.basename(__file__);

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
g_sHostArch = platform.machine();
# Map host arch to build arch.
g_enmHostArch = {
    "i386": BuildArch.X86,
    "i686": BuildArch.X86,
    "x86_64": BuildArch.AMD64,
    "amd64": BuildArch.AMD64,
    "aarch64": BuildArch.ARM64,
    "arm64": BuildArch.ARM64
}.get(g_sHostArch, BuildArch.UNKNOWN);
# By default we build for the host system.
g_enmBuildArch = g_enmHostArch;

class BuildTargets:
    """
    Supported build targets enumeration.
    This resembles the kBuild targets.
    """
    ANY = "any";
    LINUX = "linux";
    WINDOWS = "windows";
    DARWIN = "darwin";
    SOLARIS = "solaris";
    BSD = "bsd";
    HAIKU = "haiku";
    UNKNOWN = "unknown";

g_fDebug = False;             # Enables debug mode. Only for development.
g_sEnvVarPrefix = 'VBOX_';
g_fOSE = None;                # Will be determined on start.
g_sFileLog = 'configure.log'; # Log file path.
g_fHardening = True;          # Enable hardening by default.
g_cVerbosity = 0;
g_cErrors = 0;
g_cWarnings = 0;

# Defines the host target.
g_sHostTarget = platform.system().lower();
# Maps Python system string to kBuild build targets.
g_enmHostTarget = {
    "linux":    BuildTargets.LINUX,
    "win":      BuildTargets.WINDOWS,
    "darwin":   BuildTargets.DARWIN,
    "solaris":  BuildTargets.SOLARIS,
    "freebsd":  BuildTargets.BSD,
    "openbsd":  BuildTargets.BSD,
    "netbsd":   BuildTargets.BSD,
    "haiku":    BuildTargets.HAIKU,
    "":         BuildTargets.UNKNOWN
}.get(g_sHostTarget, BuildTargets.UNKNOWN);
# By default we build for the host system.
g_enmBuildTarget = g_enmHostTarget;

class BuildType:
    """
    Supported build types enumeration.
    This resembles the kBuild targets.
    """
    DEBUG = "debug";
    RELEASE = "release";
# By defaut we do a release build.
g_enmBuildType = BuildType.RELEASE;

def printError(sMessage):
    """
    Prints an error message to stderr in red.
    """
    print(f"*** Error: {sMessage}", file=sys.stderr);
    globals()['g_cErrors'] += 1;

def printVerbose(uVerbosity, sMessage):
    """
    Prints a verbose message if the global verbosity level is high enough.
    """
    if g_cVerbosity >= uVerbosity:
        print(f"--- {sMessage}");

def checkWhich(sCmdName, sToolDesc, sCustomPath=None):
    """
    Helper to check for a command in PATH or custom path.

    Returns a tuple of (command path, version string) or (None, None) if not found.
    """
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
        asSwitches = [ '--version', '-V', '/?', '/h', '/help', '-version', 'version' ];
        try:
            for sSwitch in asSwitches:
                oProc = subprocess.run([sCmdPath, sSwitch], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10);
                if oProc.returncode == 0:
                    sVer = oProc.stdout.decode('utf-8', 'replace').strip().splitlines()[0];
                    return sCmdPath, sVer;
            return sCmdPath, '<unknown>';
        except subprocess.SubprocessError as ex:
            printError(f"Error while checking version of {sToolDesc}: {str(ex)}");
        return None, None;

    printError(f"'{sCmdName}' not found in PATH.");
    return None, None;

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
        self.sIncPath = None;
        self.sLibPath = None;
        # Is a tri-state: None if not required (optional or not needed), False if required but not found, True if found.
        self.fHave = None;
        # Contains the (parsable) version string if detected.
        # Only valid if self.fHave is True.
        self.sVer = None;

    def hasCPPHeader(self):
        """
        Rough guess which headers require C++.
        """
        asCPPHdr = ["c++", "iostream", "Qt", "qt", "qglobal.h", "qcoreapplication.h"];
        return any(h for h in ([self.asIncFiles] + self.asAltIncFiles) if h and any(c in h for c in asCPPHdr));

    def getLinkerArgs(self):
        """
        Returns the linker arguments for the library as a string.
        """
        if not self.asLibFiles:
            return [];
        # Remove 'lib' prefix if present for -l on UNIX-y OSes.
        asLibArgs = [];
        for sLibCur in self.asLibFiles:
            if g_enmBuildTarget != BuildTargets.WINDOWS:
                if sLibCur.startswith("lib"):
                    sLibCur = sLibCur[3:];
                else:
                    sLibCur = ':' + sLibCur;
                asLibArgs.append(f"-l{sLibCur}");
        return asLibArgs;

    def getTestCode(self):
        """
        Return minimal program *with version print* for header check, per-library logic.
        """
        header = self.asIncFiles or (self.asAltIncFiles[0] if self.asAltIncFiles else None);
        if not header:
            return "";

        if self.sCode:
            return '#include <stdio.h>\n' + self.sCode if 'stdio.h' not in self.sCode else self.sCode;
        if self.hasCPPHeader():
            return f"#include <{header}>\n#include <iostream>\nint main() {{ std::cout << \"1\" << std::endl; return 0; }}\n"
        else:
            return f'#include <{header}>\n#include <stdio.h>\nint main(void) {{ printf("<found>"); return 0; }}\n'

    def compileAndExecute(self):
        """
        Attempts to compile and execute test code using the discovered paths and headers.
        """
        sCompiler = "g++" if self.hasCPPHeader() else "gcc";
        with tempfile.TemporaryDirectory() as sTempDir:#

            if g_fDebug:
                sTempDir = '/tmp/';

            sFilePath = os.path.join(sTempDir, "testlib.cpp" if sCompiler == "g++" else "testlib.c");
            sBinPath  = os.path.join(sTempDir, "a.out" if platform.system() != "Windows" else "a.exe");

            with open(sFilePath, "w", encoding = 'utf-8') as fh:
                fh.write(self.sCode);
            fh.close();

            sIncFlags     = f"-I{self.sIncPath}";
            sLibFlags     = f"-L{self.sLibPath}";
            asLinkerFlags = self.getLinkerArgs();
            asCmd         = [ sCompiler, sFilePath, sIncFlags, sLibFlags, "-o", sBinPath ] + asLinkerFlags;

            try:
                # Try compiling the test source file.
                oProc = subprocess.run(asCmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE, check = False, timeout = 15);
                if oProc.returncode != 0:
                    sCompilerStdErr = oProc.stderr.decode("utf-8", errors="ignore");
                    printError(sCompilerStdErr);
                else:
                    # Try executing the compiled binary and capture stdout + stderr.
                    try:
                        oProc = subprocess.run([sBinPath], stdout = subprocess.PIPE, stderr = subprocess.PIPE, check = False, timeout = 10);
                        if oProc.returncode == 0:
                            self.sVer = oProc.stdout.decode('utf-8', 'replace').strip();
                        else:
                            printError(f"Execution of test binary for {self.sName} failed with return code {oProc.returncode}:");
                            printError(oProc.stderr.decode("utf-8", errors="ignore"));
                    except subprocess.SubprocessError as ex:
                        printError(f"Execution of test binary for {self.sName} failed: {str(ex)}");
                    finally:
                        try:
                            if not g_fDebug:
                                os.remove(sBinPath);
                        except OSError as ex:
                            printError(f"Failed to remove temporary binary file {sBinPath}: {str(ex)}");
            except subprocess.SubprocessError as e:
                printError(str(e));

    def setArgs(self, args):
        """
        Applies argparse options for disabling and custom paths.
        """
        self.fDisabled = getattr(args, f"config_libs_disable_{self.sName}", False);
        self.sCustomPath = getattr(args, f"config_libs_path_{self.sName}", None);

    def getLinuxGnuTypeFromPlatform(self):
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

    def getIncSearchPaths(self):
        """
        Returns a list of existing search directories for includes.
        """
        asPaths = [];
        if self.sCustomPath:
            asPaths.extend([ os.path.join(self.sCustomPath, "include")] );
        # Use source tree lib paths first.
        asPaths.extend([ os.path.join(g_sScriptPath, "src/libs") ]);
        if g_enmBuildTarget == BuildTargets.WINDOWS:
            asRootDrivers = [ d+":" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(d+":") ];
            for r in asRootDrivers:
                asPaths.extend([ os.path.join(r, p) for p in [
                    "\\msys64\\mingw64\\include", "\\msys64\\mingw32\\include", "\\include" ]]);
                asPaths.extend([ r"c:\\Program Files", r"c:\\Program Files (x86)" ]);
        else: # Linux / MacOS / Solaris
            sGnuType = self.getLinuxGnuTypeFromPlatform();
            # Sorted by most likely-ness.
            asPaths.extend([ "/usr/include", "/usr/local/include",
                             "/usr/include/" + sGnuType, "/usr/local/include/" + sGnuType,
                             "/usr/include/" + self.sName, "/usr/local/include/" + self.sName,
                             "/opt/include", "/opt/local/include" ]);
            if g_enmBuildTarget == BuildTargets.DARWIN:
                asPaths.extend([ "/opt/homebrew/include" ]);
        return [p for p in asPaths if os.path.exists(p)];

    def getLibSearchPaths(self):
        """
        Returns a list of existing search directories for libraries.
        """
        asPaths = [];
        if self.sCustomPath:
            asPaths = [os.path.join(self.sCustomPath, "lib")];
        # Use source tree lib paths first.
        asPaths.extend([ os.path.join(g_sScriptPath, "src/libs") ]);
        if g_enmBuildTarget == BuildTargets.WINDOWS:
            root_drives = [d+":" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(d+":")];
            for r in root_drives:
                asPaths += [os.path.join(r, p) for p in [
                    "\\msys64\\mingw64\\lib", "\\msys64\\mingw32\\lib", "\\lib"]];
                asPaths += [r"c:\\Program Files", r"c:\\Program Files (x86)"];
        else:
            if g_enmBuildTarget == BuildTargets.LINUX \
            or g_enmBuildTarget == BuildTargets.SOLARIS:
                sGnuType = self.getLinuxGnuTypeFromPlatform();
                # Sorted by most likely-ness.
                asPaths = [ "/usr/lib", "/usr/local/lib",
                            "/usr/lib/" + sGnuType, "/opt/local/lib/" + sGnuType,
                            "/usr/lib64", "/lib", "/lib64",
                            "/opt/lib", "/opt/local/lib" ];
            else: # Darwin
                asPaths.append("/opt/homebrew/lib");
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
        asSearchPaths = self.getIncSearchPaths();
        for sCurSearchPath in asSearchPaths:
            for sCurHeader in asHeaderToSearch:
                sCur = os.path.join(sCurSearchPath, sCurHeader);
                if os.path.isfile(sCur):
                    self.sIncPath = sCurSearchPath;
                    return True;
                if os.sep == "\\":
                    sCur = os.path.join(sCurSearchPath, sCurHeader.replace("/", "\\"));
                    if os.path.isfile(sCur):
                        self.sIncPath = sCurSearchPath;
                        return True;

        printError(f"Header files {asHeaderToSearch} not found in paths: {asSearchPaths}");
        return False;

    def checkLib(self):
        """
        Checks for libraries in standard/custom lib paths.
        """
        if not self.asLibFiles:
            return True;
        sBasename = self.asLibFiles;
        asLibExts = [];
        if g_enmBuildTarget == BuildTargets.WINDOWS:
            asLibExts = [".lib", ".dll", ".a", ".dll.a"];
        elif g_enmBuildTarget == BuildTargets.DARWIN:
            asLibExts = [".a", ".dylib", ".so"];
        else:
            asLibExts = [".a", ".so"];
        asSearchPaths = self.getLibSearchPaths();
        for sCurSearchPath in asSearchPaths:
            for sCurExt in asLibExts:
                sPattern = os.path.join(sCurSearchPath, f"{sBasename}*{sCurExt}");
                for sCurFile in glob.glob(sPattern):
                    if os.path.isfile(sCurFile):
                        self.sLibPath = sCurSearchPath;
                        return True;

        printError(f"Library files {self.asLibFiles} not found in paths: {asSearchPaths}");
        return False;

    def performCheck(self):
        """
        Run library detection.
        """
        if g_enmBuildTarget in self.aeTargetsExcluded:
            self.fHave = None;
            return;
        if self.fDisabled:
            self.fHave = None;
            return;
        if g_enmBuildTarget in self.aeTargets \
        or BuildTargets.ANY in self.aeTargets:
            self.fHave = self.checkInc() and self.checkLib();

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
    def __init__(self, sName, asCmd = None, fnCallback = None, aeTargets = BuildTargets.ANY):
        """
        Constructor.
        """
        assert sName;

        self.sName = sName;
        self.fnCallback = fnCallback;
        self.aeTargets = aeTargets;
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
        if g_enmBuildTarget in self.aeTargets \
        or BuildTargets.ANY in self.aeTargets:
            if self.fnCallback: # Custom callback function provided?
                self.fHave = self.fnCallback(self);
            else:
                for sCmdCur in self.asCmd:
                    self.sCmdPath, self.sVer = checkWhich(sCmdCur, self.sName, self.sCustomPath);
                    if self.sCmdPath:
                        self.fHave = True;
                    else:
                        return False;
        return True;

    def getStatusString(self):
        """
        Returns a string for the tool's status.
        """
        if self.fDisabled:
            return "DISABLED";
        if self.fHave:
            return f"ok ({os.path.basename(self.sCmdPath)})";
        if self.fHave is None:
            return "?";
        return "failed";

    def __repr__(self):
        return f"{self.sName}: {self.getStatusString()}"

    def checkCallback_OpenWatcom(self):
        """
        Checks for OpenWatcom tools.
        """

        # These are the sub directories OpenWatcom ships its binaries in.
        mapBuildTarget2Bin = {
            BuildTargets.DARWIN:  "binosx",  ## @todo Still correct for Apple Silicon?
            BuildTargets.LINUX:   "binl64" if g_enmBuildArch is BuildArch.AMD64 else "arml64", # ASSUMES 64-bit.
            BuildTargets.SOLARIS: "binsol",  ## @todo Test on Solaris.
            BuildTargets.WINDOWS: "binnt",
            BuildTargets.BSD:     "binnbsd"  ## @todo Test this on FreeBSD.
        };

        sBinSubdir = mapBuildTarget2Bin.get(g_enmBuildTarget, None);
        if not sBinSubdir:
            printError(f"OpenWatcom not supported on host target {g_enmBuildTarget}.");
            return False;

        for sCmdCur in self.asCmd:
            self.sCmdPath, self.sVer = checkWhich(sCmdCur, 'OpenWatcom', os.path.join(self.sCustomPath, sBinSubdir) if self.sCustomPath else None);
            if not self.sCmdPath:
                return False;

        return True;

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
        Initializes an empty environment variable store.
        """
        self.env = {};

    def set(self, sKey, oVal):
        """
        Set the value for a given environment variable key.
        Empty values are allowed.
        """
        if isinstance(oVal, str):
            self.env[sKey] = oVal;
        elif isinstance(oVal, bool):
            self.env[sKey] = '1' if oVal is True else '';
        else:
            assert True, "Implement me!"

    def get(self, key, default=''):
        """
        Retrieves the value of an environment variable, or a default if not set (optional).
        """
        return self.env.get(key, default);

    def modify(self, key, func):
        """
        Modifies the value of an existing environment variable using a function.
        """
        if key in self.env:
            self.env[key] = str(func(self.env[key]));
        else:
            raise KeyError(f"{key} not set in environment");

    def updateFromArgs(self, args):
        """
        Updates environment variable store using a Namespace object from argparse.
        Each argument becomes an environment variable (in uppercase), set only if its value is not None.
        """
        for sKey, aValue in vars(args).items():
            if aValue is not None:
                # Search for vbox_env_ prefix to map to VBOX_* environment variables.
                if sKey.startswith('vbox_env_'):
                    sKey = sKey[len('vbox_env_'):];
                    asKeywordMap = {
                        'sete_': '',
                        'set1_': '1',
                        'set0_': '0'
                    };
                    for sPrefix, sVal in asKeywordMap.items():
                        if sKey.startswith(sPrefix):
                            sKey = sKey[len(sPrefix):];
                            aValue = sVal;
                            break;
                    sKey = g_sEnvVarPrefix + sKey;
                self.env[sKey.upper()] = aValue;

    def write(self, fh, asPrefixExclude):
        """
        Writes all stored environment variables as KEY=VALUE pairs to the given file handle.
        """
        for key, value in self.env.items():
            if asPrefixExclude and any(key.startswith(p) for p in asPrefixExclude):
                continue;
            fh.write(f"{key}={value}\n");

    def transform(self, mapTransform):
        """
        Evaluates mapping expressions and updates the affected environment variables.
        """
        for exprCur in mapTransform:
            result = exprCur(self.env);
            if isinstance(result, dict):
                self.env.update(result);

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

def show_syntax_help():
    """
    Prints syntax help.
    """
    print("Supported libraries (with configure options):\n");

    for oLibCur in g_aoLibs:
        sDisable = f"--disable-{oLibCur.name}";
        sWith    = f"--with-{oLibCur.name}-path=<path>";
        onlytxt    = " (non-Windows only)" if oLibCur.only_unix else "";
        if oLibCur.asTargets:
            onlytxt += f" (only on {oLibCur.asTargets})";
        if oLibCur.exclude_os:
            onlytxt += f" (not on {','.join(oLibCur.exclude_os)})";
        print(f"    {sDisable:<30}{sWith:<40}{onlytxt}");

    print("\nSupported tools (with configure options):\n");

    for oToolCur in g_aoTools:
        sDisable = f"--disable-{oToolCur.sName.replace('+','plus').replace('-','_')}";
        onlytxt    = f" (only on {oToolCur.aeTargets})" if oToolCur.aeTargets else "";
        print(f"    {sDisable:<30}{onlytxt}");
    print("""
    --help                         Show this help message and exit

Examples:
    ./configure.py --disable-libvpx
    ./configure.py --with-libpng-path=/usr/local
    ./configure.py --disable-yasm --disable-openwatcom
    ./configure.py --disable-libstdc++
    ./configure.py --disable-qt6

Hint: Combine any supported --disable-<lib|tool> and --with-<lib>-path=PATH options.
""");

g_aoLibs = sorted([
    ## @todo
    #LibraryCheck("berkeley-softfloat-3", [ "softfloat.h" ], [ "libsoftfloat" ],
    #             '#include <softfloat.h>\nint main() { float32_t x, y; f32_add(x, y); printf("<found>"); return 0; }\n'),
    LibraryCheck("dmtx", [ "dmtx.h" ], [ "libdmtx" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                '#include <dmtx.h>\nint main() { dmtxEncodeCreate(); printf("%s", dmtxVersion()); return 0; }\n'),
    LibraryCheck("dxvk", [ "dxvk/dxvk.h" ], [ "libdxvk" ],  [ BuildTargets.LINUX ],
                 '#include <dxvk/dxvk.h>\nint main() { printf("1"); return 0; }\n'),
    LibraryCheck("libalsa", [ "alsa/asoundlib.h" ], [ "libasound" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <alsa/asoundlib.h>\n#include <alsa/version.h>\nint main() { snd_pcm_info_sizeof(); printf("%s", SND_LIB_VERSION_STR); return 0; }\n'),
    LibraryCheck("libcap", [ "sys/capability.h" ], [ "libcap" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <sys/capability.h>\nint main() { cap_t c = cap_init(); printf("<found>"); return 0; }\n'),
    LibraryCheck("libcursor", [ "X11/cursorfont.h" ], [ "libXcursor" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <X11/Xcursor/Xcursor.h>\nint main() { printf("%d.%d", XCURSOR_LIB_MAJOR, XCURSOR_LIB_MINOR); return 0; }\n'),
    LibraryCheck("libcurl", [ "curl/curl.h" ], [ "libcurl" ], [ BuildTargets.ANY ],
                 '#include <curl/curl.h>\nint main() { printf("%s", LIBCURL_VERSION); return 0; }\n'),
    LibraryCheck("libdevmapper", [ "libdevmapper.h" ], [ "libdevmapper" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <libdevmapper.h>\nint main() { char v[64]; dm_get_library_version(v, sizeof(v)); printf("%s", v); return 0; }\n'),
    LibraryCheck("libjpeg-turbo", [ "turbojpeg.h" ], [ "libturbojpeg" ], [ BuildTargets.ANY ],
                 '#include <turbojpeg.h>\nint main() { tjInitCompress(); printf("0.0"); return 0; }\n'),
    LibraryCheck("liblzf", [ "lzf.h" ], [ "liblzf" ], [ BuildTargets.ANY ],
                 '#include <liblzf/lzf.h>\nint main() { printf("%d.%d", LZF_VERSION >> 8, LZF_VERSION & 0xff);\n#if LZF_VERSION >= 0x0105\nreturn 0;\n#else\nreturn 1;\n#endif\n }\n'),
    LibraryCheck("liblzma", [ "lzma.h" ], [ "liblzma" ], [ BuildTargets.ANY ],
                 '#include <lzma.h>\nint main() { printf("%s", lzma_version_string()); return 0; }\n'),
    LibraryCheck("libogg", [ "ogg/ogg.h" ], [ "libogg" ], [ BuildTargets.ANY ],
                 '#include <ogg/ogg.h>\nint main() { oggpack_buffer o; oggpack_get_buffer(&o); printf("<found>"); return 0; }\n'),
    LibraryCheck("libpam", [ "security/pam_appl.h" ], [ "libpam" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <security/pam_appl.h>\nint main() { \n#ifdef __LINUX_PAM__\nprintf("%d.%d", __LINUX_PAM__, __LINUX_PAM_MINOR__); if (__LINUX_PAM__ >= 1) return 0;\n#endif\nreturn 1; }\n'),
    LibraryCheck("libpng", [ "png.h" ], [ "libpng" ], [ BuildTargets.ANY ],
                 '#include <png.h>\nint main() { printf("%s", PNG_LIBPNG_VER_STRING); return 0; }\n'),
    LibraryCheck("libpthread", [ "pthread.h" ], [ "libpthread" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <unistd.h>\n#include <pthread.h>\nint main() { \n#ifdef _POSIX_VERSION\nprintf("%d", (long)_POSIX_VERSION); return 0;\n#else\nreturn 1;\n#endif\n }\n'),
    LibraryCheck("libpulse", [ "pulse/pulseaudio.h", "pulse/version.h" ], [ "libpulse" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <pulse/version.h>\nint main() { printf("%s", pa_get_library_version()); return 0; }\n'),
    LibraryCheck("libslirp", [ "slirp/libslirp.h", "slirp/libslirp-version.h" ], [ "libslirp" ], [ BuildTargets.ANY ],
                 '#include <slirp/libslirp.h>\n#include <slirp/libslirp-version.h>\nint main() { printf("%d.%d.%d", SLIRP_MAJOR_VERSION, SLIRP_MINOR_VERSION, SLIRP_MICRO_VERSION); return 0; }\n'),
    LibraryCheck("libssh", [ "libssh/libssh.h" ], [ "libssh" ], [ BuildTargets.ANY ],
                 '#include <libssh/libssh.h>\n#include <libssh/libssh_version.h>\nint main() { printf("%d.%d.%d", LIBSSH_VERSION_MAJOR, LIBSSH_VERSION_MINOR, LIBSSH_VERSION_MICRO); return 0; }\n'),
    LibraryCheck("libstdc++", [ "c++/11/iostream" ], [ ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 "#include <iostream>\nint main() { \n #ifdef __GLIBCXX__\nstd::cout << __GLIBCXX__;\n#elif defined(__GLIBCPP__)\nstd::cout << __GLIBCPP__;\n#else\nreturn 1\n#endif\nreturn 0; }\n",
                 asAltIncFiles = [ "c++/4.8.2/iostream", "c++/iostream" ]),
    LibraryCheck("libtpms", [ "libtpms/tpm_library.h" ], [ "libtpms" ], [ BuildTargets.ANY ],
                 '#include <libtpms/tpm_library.h>\nint main() { printf("%d.%d.%d", TPM_LIBRARY_VER_MAJOR, TPM_LIBRARY_VER_MINOR, TPM_LIBRARY_VER_MICRO); return 0; }\n'),
    LibraryCheck("libvncserver", [ "rfb/rfb.h", "rfb/rfbclient.h" ], [ "libvncserver" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <rfb/rfb.h>\nint main() { printf("%s", LIBVNCSERVER_PACKAGE_VERSION); return 0; }\n'),
    LibraryCheck("libvorbis", [ "vorbis/vorbisenc.h" ], [ "libvorbis", "libvorbisenc" ], [ BuildTargets.ANY ],
                 '#include <vorbis/vorbisenc.h>\nint main() { vorbis_info v; vorbis_info_init(&v); int vorbis_rc = vorbis_encode_init_vbr(&v, 2 /* channels */, 44100 /* hz */, (float).4 /* quality */); printf("<found>"); return 0; }\n'),
    LibraryCheck("libvpx", [ "vpx/vpx_decoder.h" ], [ "libvpx" ], [ BuildTargets.ANY ],
                 '#include <vpx/vpx_codec.h>\nint main() { printf("%s", vpx_codec_version_str()); return 0; }\n'),
    LibraryCheck("libxml2", [ "libxml/parser.h" ] , [ "libxml2" ], [ BuildTargets.ANY ],
                 '#include <libxml/xmlversion.h>\nint main() { printf("%s", LIBXML_DOTTED_VERSION); return 0; }\n'),
    LibraryCheck("zlib1g", [ "zlib.h" ], [ "libz" ], [ BuildTargets.ANY ],
                 '#include <zlib.h>\nint main() { printf("%s", ZLIB_VERSION); return 0; }\n'),
    LibraryCheck("lwip", [ "lwip/init.h" ], [ "liblwip" ], [ BuildTargets.ANY ],
                 '#include <lwip/init.h>\nint main() { printf("%d.%d.%d", LWIP_VERSION_MAJOR, LWIP_VERSION_MINOR, LWIP_VERSION_REVISION); return 0; }\n'),
    LibraryCheck("opengl", [ "GL/gl.h" ], [ "libGL" ], [ BuildTargets.ANY ],
                 '#include <GL/gl.h>\n#include <stdio.h>\nint main() { const GLubyte *s = glGetString(GL_VERSION); printf("%s", s ? (const char *)s : "<found>"); return 0; }\n'),
    LibraryCheck("qt6", [ "QtCore/qconfig.h" ], [ "libQt6Core" ], [ BuildTargets.ANY ],
                 '#include <stdio.h>\n#include <qt6/QtCore/qconfig.h>\nint main() { printf("%s", QT_VERSION_STR); }',
                 asAltIncFiles = [ "qt/QtCore/qglobal.h", "QtCore/qcoreapplication.h", "qt6/QtCore/qcoreapplication.h" ] ),
    LibraryCheck("sdl2", [ "SDL2/SDL.h" ], [ "libSDL2" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <SDL2/SDL.h>\nint main() { printf("%d.%d.%d", SDL_MAJOR_VERSION, SDL_MINOR_VERSION, SDL_PATCHLEVEL); return 0; }\n',
                 asAltIncFiles = [ "SDL.h" ]),
    LibraryCheck("sdl2_ttf", [ "SDL2/SDL_ttf.h" ], [ "libSDL2_ttf" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <SDL2/SDL_ttf.h>\nint main() { printf("%d.%d.%d", SDL_TTF_MAJOR_VERSION, SDL_TTF_MINOR_VERSION, SDL_TTF_PATCHLEVEL); return 0; }\n',
                 asAltIncFiles = [ "SDL_ttf.h" ]),
    LibraryCheck("x11", [ "X11/Xlib.h" ], [ "libX11" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <X11/Xlib.h>\nint main() { XOpenDisplay(NULL); printf("<found>"); return 0; }\n'),
    LibraryCheck("xext", [ "X11/extensions/Xext.h" ], [ "libXext" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <X11/Xlib.h>\n#include <X11/extensions/Xext.h>\nint main() { XSetExtensionErrorHandler(NULL); printf("<found>"); return 0; }\n'),
    LibraryCheck("xmu", [ "X11/Xmu/Xmu.h" ], [ "libXmu" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <X11/Xmu/Xmu.h>\nint main() { XmuMakeAtom("test"); printf("<found>"); return 0; }\n', aeTargetsExcluded=[ BuildTargets.DARWIN ]),
    LibraryCheck("xrandr", [ "X11/extensions/Xrandr.h" ], [ "libXrandr", "libX11" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <X11/Xlib.h>\n#include <X11/extensions/Xrandr.h>\nint main() { Display *dpy = XOpenDisplay(NULL); Window root = RootWindow(dpy, 0); XRRScreenConfiguration *c = XRRGetScreenInfo(dpy, root); printf("<found>"); return 0; }\n'),
    LibraryCheck("libxinerama", [ "X11/extensions/Xinerama.h" ], [ "libXinerama", "libX11" ], [ BuildTargets.LINUX, BuildTargets.SOLARIS, BuildTargets.BSD ],
                 '#include <X11/Xlib.h>\n#include <X11/extensions/Xinerama.h>\nint main() { Display *dpy = XOpenDisplay(NULL); XineramaIsActive(dpy); printf("<found>"); return 0; }\n')
], key=lambda l: l.sName);

g_aoTools = sorted([
    ToolCheck("gsoap", asCmd = [ "soapcpp2", "wsdl2h" ]),
    ToolCheck("java", asCmd = [ "java" ]),
    ToolCheck("kbuild", asCmd = [ "kmk" ]),
    ToolCheck("makeself", asCmd = [ "makeself" ], aeTargets = [ BuildTargets.LINUX ]),
    ToolCheck("openwatcom", asCmd = [ "wcl", "wcl386", "wlink" ], fnCallback = ToolCheck.checkCallback_OpenWatcom ),
    ToolCheck("xcode", asCmd = [], fnCallback = ToolCheck.checkCallback_XCode, aeTargets = [ BuildTargets.DARWIN ]),
    ToolCheck("yasm", asCmd = [ 'yasm' ], aeTargets = [ BuildTargets.LINUX ]),
], key=lambda t: t.sName.lower())

def write_autoconfig_kmk(sFilePath, oEnv, aoLibs, aoTools):
    """
    Writes the AutoConfig.kmk file with SDK paths and enable/disable flags.
    Each library/tool gets VBOX_WITH_<NAME>, SDK_<NAME>_LIBS, SDK_<NAME>_INCS.
    """

    _ = aoTools; # Unused for now.

    try:
        with open(sFilePath, "w", encoding = "utf-8") as fh:
            fh.write(f"""
# -*- Makefile -*-
#
# Generated by {g_sScriptName}.
#
# DO NOT EDIT THIS FILE MANUALLY
# It will be completely overwritten if {g_sScriptName} is executed again.
#
# Generated on """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """
#
\n""");
            oEnv.write(fh, asPrefixExclude = ['CONFIG_'] );
            fh.write('\n');

            for oLibCur in aoLibs:
                sVarBase = oLibCur.sName.upper().replace("+", "PLUS").replace("-", "_");
                fEnabled = 1 if oLibCur.fHave else 0;
                fh.write(f"VBOX_WITH_{sVarBase}={fEnabled}\n");
                if oLibCur.fHave and (oLibCur.sLibPath or oLibCur.sIncPath):
                    if oLibCur.sLibPath:
                        fh.write(f"SDK_{sVarBase}_LIBS={oLibCur.sLibPath}\n");
                    if oLibCur.sIncPath:
                        fh.write(f"SDK_{sVarBase}_INCS={oLibCur.sIncPath}\n");

        return True;
    except OSError as ex:
        printError(f"Failed to write AutoConfig.kmk to {sFilePath}: {str(ex)}");
    return False;

def write_env(sFilePath, oEnv, aoLibs, aoTools):
    """
    Writes the env.sh file with SDK paths and enable/disable flags.
    Each library/tool gets VBOX_WITH_<NAME>, SDK_<NAME>_LIBS, SDK_<NAME>_INCS.
    """

    _ = oEnv, aoLibs, aoTools; # Unused for now.

    try:
        with open(sFilePath, "w", encoding = "utf-8") as fh:
            fh.write(f"""
# -*- Environment -*-
#
# Generated by {g_sScriptName}.
#
# DO NOT EDIT THIS FILE MANUALLY
# It will be completely overwritten if {g_sScriptName} is executed again.
#
# Generated on """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f"""
#

KBUILD_HOST={g_enmHostTarget}
KBUILD_HOST_ARCH={g_sHostArch}
KBUILD_TARGET={g_enmBuildTarget}
KBUILD_TARGET_ARCH={g_enmBuildArch}
KBUILD_TARGET_CPU={g_enmBuildArch}
KBUILD_TYPE={g_enmBuildType}
export KBUILD_HOST KBUILD_HOST_ARCH KBUILD_TARGET KBUILD_TARGET_ARCH KBUILD_TARGET_CPU KBUILD_TYPE
""");
        return True;
    except OSError as ex:
        printError(f"Failed to write env.sh to {sFilePath}: {str(ex)}");
    return False;

def main():
    """
    Main entry point.
    """
    global g_cVerbosity;
    global g_fDebug;
    global g_fOSE;
    global g_sFileLog;

    #
    # argparse config namespace rules:
    # - Everything internally used is prefixed with 'config_'.
    # - Library options are prefixed with 'config_libs_'.
    # - Tool options are prefixed with 'config_tools_'.
    # - VirtualBox-specific environment variables (VBOX_WITH_, VBOX_ONLY_ and so on) are prefixed with 'vbox_env_'.
    #
    # 'vbox_env' prefix rules:
    # - 'vbox_env_sete_': Sets the env variable to empty (e.g. VBOX_WITH_DOCS="").
    # - 'vbox_env_set1_': Sets the env variable to 1 (e.g. VBOX_WITH_DOCS=1).
    # - 'vbox_env_set0_': Sets the env variable to 0 (e.g. VBOX_WITH_DOCS=0).
    #
    oParser = argparse.ArgumentParser(add_help=False);
    oParser.add_argument('--help', help="Displays this help");
    oParser.add_argument('-v', '--verbose', help="Enables verbose output", action='count', default=0, dest='config_verbose');
    oParser.add_argument('-V', '--version', help="Prints the version of this script");
    for oLibCur in g_aoLibs:
        oParser.add_argument(f'--disable-{oLibCur.sName}', action='store_true', default=None, dest=f'config_libs_disable_{oLibCur.sName}');
        oParser.add_argument(f'--with-{oLibCur.sName}-path', dest=f'config_libs_path_{oLibCur.sName}');
        oParser.add_argument(f'--only-{oLibCur.sName}', action='store_true', default=None, dest=f'config_libs_only_{oLibCur.sName}');
    for oToolCur in g_aoTools:
        oParser.add_argument(f'--disable-{oToolCur.sName}', action='store_true', default=None, dest=f'config_tools_disable_{oToolCur.sName}');
        oParser.add_argument(f'--with-{oToolCur.sName}-path', dest=f'config_tools_path_{oToolCur.sName}');
        oParser.add_argument(f'--only-{oToolCur.sName}', action='store_true', default=None, dest=f'config_tools_only_{oToolCur.sName}');
    oParser.add_argument('--disable-docs', help='Disables building the documentation', action='store_true', default=None, dest='vbox_env_sete_with_docs');
    oParser.add_argument('--disable-python', help='Disables building the Python bindings', action='store_true', default=None);
    oParser.add_argument('--with-hardening', help='Enables or disables hardening', action='store_true', default=None);
    oParser.add_argument('--without-hardening', help='Enables or disables hardening', action='store_true', default=None);
    oParser.add_argument('--file-autoconfig', help='Path to output AutoConfig.kmk file', action='store_true', default='AutoConfig.kmk', dest='config_file_autoconfig');
    oParser.add_argument('--file-env', help='Path to output env.sh file', action='store_true', default='env.sh', dest='config_file_env');
    oParser.add_argument('--file-log', help='Path to output log file', action='store_true', default='configure.log', dest='config_file_log');
    oParser.add_argument('--only-additions', help='Only build Guest Additions related libraries and tools', action='store_true', default=None, dest='vbox_only_additions');
    oParser.add_argument('--only-docs', help='Only build the documentation', action='store_true', default=None, dest='vbox_env_set1_only_docs');
    oParser.add_argument('--ose', help='Builds the OSE version', action='store_true', default=None, dest='vbox_env_set1_ose');
    oParser.add_argument('--debug', help='Runs in debug mode. Only use for development', action='store_true', default=False, dest='config_debug');

    try:
        oArgs = oParser.parse_args();
    except argparse.ArgumentError as e:
        printError(f"Argument error: {str(e)}");
        return 2;

    g_cVerbosity = oArgs.config_verbose;
    g_fDebug = oArgs.config_debug;
    g_sFileLog = oArgs.config_file_log;

    # Filter libs and tools based on --only-XXX flags.
    aoOnlyLibs = [lib for lib in g_aoLibs if getattr(oArgs, f'config_libs_only_{lib.sName}', False)];
    aoOnlyTools = [tool for tool in g_aoTools if getattr(oArgs, f'config_tools_only_{tool.sName}', False)];
    aoLibsToCheck = aoOnlyLibs if aoOnlyLibs else g_aoLibs;
    aoToolsToCheck = aoOnlyTools if aoOnlyTools else g_aoTools;
    # Filter libs and tools based on build target.
    aoLibsToCheck  = [lib for lib in aoLibsToCheck if g_enmBuildTarget in lib.aeTargets or BuildTargets.ANY in lib.aeTargets];
    aoToolsToCheck = [tool for tool in aoToolsToCheck if g_enmBuildTarget in tool.aeTargets or BuildTargets.ANY in tool.aeTargets];

    if oArgs.help:
        show_syntax_help();
        return 2;
    if oArgs.version:
        print('1.0'); ## @todo Return SVN rev.
        return 0;

    logf = open(g_sFileLog, "w", encoding="utf-8");
    sys.stdout = Log(sys.stdout, logf);
    sys.stderr = Log(sys.stderr, logf);

    print( 'VirtualBox configuration script');
    print();
    print(f'Running on {platform.system()} {platform.release()} ({platform.machine()})');
    print();
    print(f'Host OS / arch     : {g_sHostTarget}.{g_sHostArch}');
    print(f'Building for target: {g_enmBuildTarget}.{g_enmBuildArch}');
    print();

    oEnv = EnvManager();
    oEnv.updateFromArgs(oArgs);

    #
    # Handle OSE building.
    #
    g_fOSE = oArgs.vbox_env_set1_ose;
    if   not g_fOSE \
    and os.path.exists('src/VBox/ExtPacks/Puel/ExtPack.xml'):
        print('Found ExtPack, assuming to build PUEL version');
        g_fOSE = False;
    print('Building %s version' % ('OSE' if (g_fOSE is None or g_fOSE is True) else 'PUEL'));
    print();
    oEnv.set('VBOX_OSE', g_fOSE);

    #
    # Handle environment variable transformations.
    #
    # This is needed to set/unset/change other environment variables on already set ones.
    # For instance, building OSE requires certain components to be disabled. Same when a certain library gets disabled.
    #
    envTransforms = [
        # Disabling building the docs when only building Additions or explicitly disabled building the docs.
        lambda env: { 'VBOX_WITH_DOCS_PACKING': ''} if oEnv.get('VBOX_ONLY_ADDITIONS') or oEnv.get('VBOX_WITH_DOCS') == '' else {},
        # Disable building the ExtPack VNC when only building Additions or OSE.
        lambda env: { 'VBOX_WITH_EXTPACK_VNC': '' } if oEnv.get('VBOX_ONLY_ADDITIONS') or oEnv.get('VBOX_OSE') == '1' else {},
        lambda env: { 'VBOX_WITH_WEBSERVICES': '' } if oEnv.get('VBOX_ONLY_ADDITIONS') else {},
        # Disable stuff which aren't available in OSE.
        lambda env: { 'VBOX_WITH_VALIDATIONKIT': '' , 'VBOX_WITH_WIN32_ADDITIONS': '' } if oEnv.get('VBOX_OSE') else {},
        lambda env: { 'VBOX_WITH_EXTPACK_PUEL_BUILD': '' } if oEnv.get('VBOX_ONLY_ADDITIONS') else {},
        lambda env: { 'VBOX_WITH_QTGUI': '' } if oEnv.get('CONFIG_LIBS_DISABLE_QT') else {}
    ];
    oEnv.transform(envTransforms);

    if g_cVerbosity >= 2:
        printVerbose(2, 'Environment manager variables:');
        print(oEnv.env);

    #
    # Perform OS tool checks.
    # These are essential and must be present for all following checks.
    #
    aOsTools = {
        BuildTargets.LINUX:   [ 'gcc', 'make', 'pkg-config' ],
        BuildTargets.DARWIN:  [ 'clang', 'make', 'brew' ],
        BuildTargets.WINDOWS: [ 'cl', 'gcc', 'nmake', 'cmake', 'msbuild' ],
        BuildTargets.SOLARIS: [ 'cc', 'gmake', 'pkg-config' ]
    };
    aOsToolsToCheck = aOsTools.get(g_enmBuildTarget, []);
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
    if g_cErrors == 0:
        print();
        for oToolCur in aoToolsToCheck:
            oToolCur.setArgs(oArgs);
            oToolCur.performCheck();

    #
    # Perform library checks.
    #
    if g_cErrors == 0:
        print();
        for oLibCur in aoLibsToCheck:
            oLibCur.setArgs(oArgs);
            oLibCur.performCheck();
            if oLibCur.fHave:
                oLibCur.compileAndExecute();
    #
    # Print summary.
    #
    if g_cErrors == 0:

        oToolsTable = SimpleTable([ 'Tool', 'Status', 'Version', 'Path' ]);
        for oToolCur in aoToolsToCheck:
            oToolsTable.addRow(( oToolCur.sName,
                                 oToolCur.getStatusString().split()[0],
                                 oToolCur.sVer if oToolCur.sVer else '-',
                                 oToolCur.sCmdPath if oToolCur.sCmdPath else '-' ));
        print();
        oToolsTable.print();
        print();

        oLibsTable = SimpleTable([ 'Library', 'Status', 'Version', 'Include Path' ]);
        for oLibCur in aoLibsToCheck:
            oLibsTable.addRow(( oLibCur.sName,
                                oLibCur.getStatusString().split()[0],
                                oLibCur.sVer if oLibCur.sVer else '-',
                                oLibCur.sIncPath if oLibCur.sIncPath else '-' ));
        print();
        oLibsTable.print();
        print();

    if g_cErrors == 0:
        if write_autoconfig_kmk(oArgs.config_file_autoconfig, oEnv, g_aoLibs, g_aoTools):
            if write_env(oArgs.config_file_env, oEnv, g_aoLibs, g_aoTools):
                print();
                print(f'Successfully generated \"{oArgs.config_file_autoconfig}\" and \"{oArgs.config_file_env}\".');
                print();
                print(f'Source {oArgs.config_file_env} once before you start to build VirtualBox:');
                print(f'  source "{oArgs.config_file_env}"');
                print();
                print( 'Then run the build with:');
                print( '  kmk');
                print();

        if g_enmBuildTarget == BuildTargets.LINUX:
            print('To compile the kernel modules, do:');
            print();
            print('  cd $out_base_dir/out/$OS.$TARGET_MACHINE/$BUILD_TYPE/bin/src');
            print('  make');
            print();

        if oArgs.vbox_only_additions:
            print();
            print('Tree configured to build only the Guest Additions');
            print();

        if g_fHardening:
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
    if g_cErrors:
        print(f'\nConfiguration failed with {g_cErrors} error(s). See {g_sFileLog} for details.');

    print('\nWork in progress! Do not use for production builds yet!\n');

    logf.close();
    return 0 if g_cErrors == 0 else 1;

if __name__ == "__main__":
    sys.exit(main());
