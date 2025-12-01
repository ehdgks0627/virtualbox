#!/usr/bin/env python3
"""
Configuration script for building VirtualBox.
"""

# -*- coding: utf-8 -*-
# $Id: configure.py 111968 2025-12-01 17:06:39Z andreas.loeffler@oracle.com $
# pylint: disable=global-statement
# pylint: disable=line-too-long
# pylint: disable=too-many-lines
# pylint: disable=unnecessary-semicolon
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
g_sOutPath    = os.path.join(g_sScriptPath, 'out');

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
g_fNoFatal = False;           # Continue on fatal errors.
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

def checkWhich(sCmdName, sToolDesc, sCustomPath = None, asVersionSwitches = None):
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
        asCPPHdr = ['c++", "iostream", "Qt", "qt", "qglobal.h", "qcoreapplication.h'];
        return any(h for h in ([self.asIncFiles] + self.asAltIncFiles) if h and any(c in h for c in asCPPHdr));

    def getLinkerArgs(self, enmBuildTarget):
        """
        Returns the linker arguments for the library as a string.

        Returns None for no libs.
        """
        if not self.asLibFiles:
            return None;
        # Remove 'lib' prefix if present for -l on UNIX-y OSes.
        asLibArgs = '';
        for sLibCur in self.asLibFiles:
            if enmBuildTarget == BuildTarget.WINDOWS:
                asLibArgs += f"{sLibCur} ";
            else:
                if sLibCur.startswith("lib"):
                    sLibCur = sLibCur[3:];
                else:
                    sLibCur = ':' + sLibCur;
                asLibArgs += f"-l{sLibCur} ";
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

    def compileAndExecute(self, enmBuildTarget, enmBuildArch):
        """
        Attempts to compile and execute test code using the discovered paths and headers.
        """

        _ = enmBuildArch;
        if enmBuildTarget == BuildTarget.WINDOWS:
            sCompiler = 'cl';
        else:
            sCompiler = 'g++' if self.hasCPPHeader() else 'gcc';

        with tempfile.TemporaryDirectory() as sTempDir:

            if g_fDebug:
                sTempDir = '/tmp/';

            sFilePath = os.path.join(sTempDir, "testlib.cpp" if sCompiler == "g++" else "testlib.c");
            sBinPath  = os.path.join(sTempDir, "a.out" if enmBuildTarget != BuildTarget.WINDOWS else "a.exe");

            with open(sFilePath, "w", encoding = 'utf-8') as fh:
                fh.write(self.sCode);
            fh.close();

            if enmBuildTarget == BuildTarget.WINDOWS:
                sIncFlags     = f'/I"{self.sIncPath}"';
                sLibFlags     = f'/LIBPATH:"{self.sLibPath}"';
                asLinkerFlags = self.getLinkerArgs(enmBuildTarget);
                asCmd         = [ sCompiler, sFilePath, sIncFlags, sLibFlags, "/Fe:" + sBinPath ] + asLinkerFlags;
            else:
                sIncFlags     = f"-I{self.sIncPath}";
                sLibFlags     = f"-L{self.sLibPath}";
                asLinkerFlags = self.getLinkerArgs(enmBuildTarget);
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
        if  g_oEnv['KBUILD_TARGET'] == BuildTarget.WINDOWS:
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
            if  g_oEnv['KBUILD_TARGET'] == BuildTarget.DARWIN:
                asPaths.extend([ "/opt/homebrew/include" ]);

        asPathMatched = [];
        for sPathCur in asPaths:
            sPattern = sPathCur + '-*';
            asPathMatched.extend(glob.glob(sPattern));
        asPaths = asPathMatched + asPaths; # Put at the beginning.

        return [p for p in asPaths if os.path.isdir(p)];

    def getLibSearchPaths(self):
        """
        Returns a list of existing search directories for libraries.
        """
        asPaths = [];
        if self.sCustomPath:
            asPaths = [os.path.join(self.sCustomPath, "lib")];
        if  g_oEnv['KBUILD_TARGET'] == BuildTarget.WINDOWS:
            root_drives = [d+":" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(d+":")];
            for r in root_drives:
                asPaths += [os.path.join(r, p) for p in [
                    '\\msys64\\mingw64\\lib', '\\msys64\\mingw32\\lib', '\\lib']];
                asPaths += [r'c:\\Program Files', r'c:\\Program Files (x86)'];
        else:
            if  g_oEnv['KBUILD_TARGET'] == BuildTarget.LINUX \
            or  g_oEnv['KBUILD_TARGET'] == BuildTarget.SOLARIS:
                sGnuType = self.getLinuxGnuTypeFromPlatform();
                # Sorted by most likely-ness.
                asPaths.extend([ "/usr/lib", "/usr/local/lib",
                                 "/usr/lib/" + sGnuType, "/opt/local/lib/" + sGnuType,
                                 "/usr/lib64", "/lib", "/lib64",
                                 "/opt/lib", "/opt/local/lib" ]);
            else: # Darwin
                asPaths.append("/opt/homebrew/lib");

        asPathMatched = [];
        for sPathCur in asPaths:
            sPattern = sPathCur + '-*';
            asPathMatched.extend(glob.glob(sPattern));
        asPaths = asPathMatched + asPaths; # Put at the beginning.

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
            printVerbose(1, f'Checking include path for {self.sName}: {sCurSearchPath}');
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
        if  g_oEnv['KBUILD_TARGET'] == BuildTarget.WINDOWS:
            asLibExts = ['.lib", ".dll", ".a", ".dll.a'];
        elif  g_oEnv['KBUILD_TARGET'] == BuildTarget.DARWIN:
            asLibExts = ['.a", ".dylib", ".so'];
        else:
            asLibExts = ['.a", ".so'];
        asSearchPaths = self.getLibSearchPaths();
        for sCurSearchPath in asSearchPaths:
            printVerbose(1, f'Checking library path for {self.sName}: {sCurSearchPath}');
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
        if  g_oEnv['KBUILD_TARGET'] in self.aeTargetsExcluded:
            self.fHave = None;
            return;
        if self.fDisabled:
            self.fHave = None;
            return;
        if  g_oEnv['KBUILD_TARGET'] in self.aeTargets \
        or BuildTarget.ANY in self.aeTargets:
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

    def getWinProgramFiles(self):
        """
        Returns a list of existing Windows "Program Files" directories.

        @todo Cache this?
        """
        asPaths = [];
        for sEnv in [ 'ProgramFiles', r'C:\Program File' \
                      'ProgramFiles(x86)', r'C:\Program Files (x86)' ]:
            sPath = os.environ.get(sEnv);
            if sPath and os.path.exists(sPath):
                asPaths.extend([ sPath ]);
        return asPaths;

    def checkCallback_VisualCPP(self):
        """
        Checks for Visual C++ version 16 (2019), 15 (2017), 14 (2015), 12 (2013), 11 (2012) or 10 (2010).
        """

        # Since v2017 we can use vswhere.exe, so try using that first.
        sVCPPVer = None;
        sVCPPPath = None;
        for sProgramPath in self.getWinProgramFiles():
            sPath = os.path.join(sProgramPath, 'Microsoft Visual Studio', 'Installer', 'vswhere.exe');
            if os.path.isfile(sPath):
                asCmd = [ sPath,
                          '-products', '*',
                          '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                          '-property', 'installationVersion,displayName,installationPath',
                          '-format', 'json' ];
                oProc = subprocess.run(asCmd, capture_output = True, check = False, text = True);
                if oProc.returncode == 0 and oProc.stdout.strip():
                    import json
                    asList = json.loads(oProc.stdout);
                    for curProd in asList:
                        sVCPPVer  = curProd.get("installationVersion", None);
                        sVCPPPath = curProd.get("installationPath", None);
                        print(f'Found {curProd.get("displayName", "")} {sVCPPVer} at {sVCPPPath}');
                        break;
            if sVCPPVer:
                break;

        # For older versions we have to use the registry. Start with "newest" first.
        if not sVCPPVer:
            import winreg
            for uVer, sName in [(14, "2015"), (12, "2013"), (11, "2012"), (10, "2010")]:
                try:
                    sKey = r'SOFTWARE\Microsoft\VisualStudio\{}.0\Setup\VC'.format(uVer);
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sKey) as k:
                        sVCPPPath, _ = winreg.QueryValueEx(k, "ProductDir");
                        sVCPPVer     = sName;
                        break;
                except FileNotFoundError:
                    pass;

        if sVCPPVer:
            print(f'Found Visual C++ {sVCPPVer} at "{sVCPPPath}"');

            g_oEnv.set('VBOX_VCC_TOOL_STEM', sVCPPVer);
            g_oEnv.set(f'PATH_TOOL_{sVCPPVer}', sVCPPPath);
            g_oEnv.set(f'PATH_TOOL_{sVCPPVer}X86', sVCPPPath);
            g_oEnv.set(f'PATH_TOOL_{sVCPPVer}AMD64', sVCPPPath);
            ## @todo ARM?

            ## @todo VBOX_WITH_NEW_VCC?

        return True if sVCPPVer else False;

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
            print(f'kBuild devtools found at {sPathDevTools}');
            g_oEnv.set('KBUILD_DEVTOOLS', sPathDevTools);
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
        return False;

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

    def set(self, sKey, sVal):
        """
        Set the value for a given environment variable key.
        Empty values are allowed.
        None values skips setting altogether (practical for inline comparison).
        """
        if sVal is None:
            return;
        assert isinstance(sVal, str);
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
        Each argument becomes an environment variable (in uppercase), set only if its value is not None.
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

    def write(self, fh, asPrefixExclude):
        """
        Writes all stored environment variables as KEY=VALUE pairs to the given file handle.
        """
        for sKey, sVal in self.env.items():
            if asPrefixExclude and any(sKey.startswith(p) for p in asPrefixExclude):
                continue;
            if sVal: # Might be None.
                fh.write(f"{sKey}={sVal}\n");

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
    ## @todo
    #LibraryCheck("berkeley-softfloat-3", [ "softfloat.h" ], [ "libsoftfloat" ],
    #             '#include <softfloat.h>\nint main() { float32_t x, y; f32_add(x, y); printf("<found>"); return 0; }\n'),
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
                 "#include <iostream>\nint main() { \n #ifdef __GLIBCXX__\nstd::cout << __GLIBCXX__;\n#elif defined(__GLIBCPP__)\nstd::cout << __GLIBCPP__;\n#else\nreturn 1\n#endif\nreturn 0; }\n",
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

g_aoTools = sorted([
    ToolCheck("gcc", asCmd = [ "gcc" ], fnCallback = ToolCheck.checkCallback_gcc, aeTargets = [ BuildTarget.LINUX, BuildTarget.SOLARIS ] ),
    ToolCheck("devtools", asCmd = [ ], fnCallback = ToolCheck.checkCallback_devtools ),
    ToolCheck("gsoap", asCmd = [ "soapcpp2", "wsdl2h" ]),
    ToolCheck("java", asCmd = [ "java" ]),
    ToolCheck("kbuild", asCmd = [ "kbuild" ], fnCallback = ToolCheck.checkCallback_kBuild ),
    ToolCheck("makeself", asCmd = [ "makeself" ], aeTargets = [ BuildTarget.LINUX ]),
    ToolCheck("openwatcom", asCmd = [ "wcl", "wcl386", "wlink" ], fnCallback = ToolCheck.checkCallback_OpenWatcom ),
    ToolCheck("visualcpp", asCmd = [ ], fnCallback = ToolCheck.checkCallback_VisualCPP ),
    ToolCheck("xcode", asCmd = [], fnCallback = ToolCheck.checkCallback_XCode, aeTargets = [ BuildTarget.DARWIN ]),
    ToolCheck("yasm", asCmd = [ 'yasm' ], aeTargets = [ BuildTarget.LINUX ]),
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
            oEnv.write(fh, asPrefixExclude = ['CONFIG_', 'KBUILD_'] );
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
    Writes the env.sh file with kBuild configuration and other tools stuff.
    """

    _ = aoLibs, aoTools; # Unused for now.

    try:
        with open(sFilePath, "w", encoding = "utf-8") as fh:
            fh.write(f"""
# -*- Environment -*-
#
# Automatically generated by
#
#   {g_sScriptName} """ + ' '.join(sys.argv[1:]) + f"""
#
# DO NOT EDIT THIS FILE MANUALLY
# It will be completely overwritten if {g_sScriptName} is executed again.
#
# Generated on """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f"""
#

KBUILD_HOST={g_enmHostTarget}
KBUILD_HOST_ARCH={g_sHostArch}
KBUILD_TARGET={ oEnv['KBUILD_TARGET'] }
KBUILD_TARGET_ARCH={ oEnv['KBUILD_TARGET_ARCH'] }
KBUILD_TARGET_CPU={ oEnv['KBUILD_TARGET_ARCH'] }
KBUILD_TYPE={ oEnv['KBUILD_TYPE'] }
export KBUILD_HOST KBUILD_HOST_ARCH KBUILD_TARGET KBUILD_TARGET_ARCH KBUILD_TARGET_CPU KBUILD_TYPE
KBUILD_PATH={ oEnv['KBUILD_PATH'] }
""");

            sPath = oEnv['KBUILD_DEVTOOLS'];
            if sPath:
                fh.writef(f'KBUILD_DEVTOOLS={sPath}\n');
                fh.writef( 'export KBUILD_PATH KBUILD_DEVTOOLS\n');
            sPath = oEnv['PATH_OUT_BASE'];
            if sPath:
                fh.write(f'PATH_OUT_BASE={sPath}\n');
                fh.write( 'export PATH_OUT_BASE\n');

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
    global g_fNoFatal;
    global g_sFileLog;

    #
    # argparse config namespace rules:
    # - Everything internally used is prefixed with 'config_'.
    # - Library options are prefixed with 'config_libs_'.
    # - Tool options are prefixed with 'config_tools_'.
    # - VirtualBox-specific environment variables (VBOX_WITH_, VBOX_ONLY_ and so on) are written as-is (e.g. 'vbox_with_docs=1'),
    #   including the value to be set.
    #
    oParser = argparse.ArgumentParser(add_help=False);
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

    oParser.add_argument('--disable-docs', help='Disables building the documentation', action='store_true', default=None, dest='vbox_with_docs=');
    oParser.add_argument('--disable-python', help='Disables building the Python bindings', action='store_true', default=None, dest='vbox_with_python=');
    oParser.add_argument('--disable-pylint', help='Disables using pylint', action='store_true', default=None, dest='vbox_with_pylint=');
    oParser.add_argument('--disable-sdl', help='Disables building the SDL frontend', action='store_true', default=None, dest='vbox_with_sdl=');
    oParser.add_argument('--disable-udptunnel', help='Disables building UDP tunnel support', action='store_true', default=None, dest='vbox_with_udptunnel=');
    oParser.add_argument('--with-hardening', help='Enables or disables hardening', action='store_true', default=None, dest='vbox_with_hardening=1');
    oParser.add_argument('--without-hardening', help='Enables or disables hardening', action='store_true', default=None, dest='vbox_with_hardening=');
    oParser.add_argument('--file-autoconfig', help='Path to output AutoConfig.kmk file', action='store_true', default='AutoConfig.kmk', dest='config_file_autoconfig');
    oParser.add_argument('--file-env', help='Path to output env[.bat|.sh] file', action='store_true', \
                         default='env.bat' if g_enmHostTarget == BuildTarget.WINDOWS else 'env.sh', dest='config_file_env');
    oParser.add_argument('--file-log', help='Path to output log file', action='store_true', default='configure.log', dest='config_file_log');
    oParser.add_argument('--only-additions', help='Only build Guest Additions related libraries and tools', action='store_true', default=None, dest='vbox_only_additions=');
    oParser.add_argument('--only-docs', help='Only build the documentation', action='store_true', default=None, dest='vbox_only_docs=1');
    oParser.add_argument('--path-out-base', help='Specifies the output directory', action='store', default=None, dest='config_path_out_base');
    oParser.add_argument('--ose', help='Builds the OSE version', action='store_true', default=None, dest='vbox_ose=1');
    oParser.add_argument('--debug', help='Runs in debug mode. Only use for development', action='store_true', default=False, dest='config_debug');
    oParser.add_argument('--nofatal', help='Continues execution on fatal errors', action='store_true', dest='config_nofatal');
    oParser.add_argument('--build-profile', help='Build with a profiling support', action='store_true', default=None, dest='kbuild_type=profile');
    oParser.add_argument('--build-target', help='Specifies the build target', action='store_true', default=None, dest='config_build_target');
    oParser.add_argument('--build-arch', help='Specifies the build architecture', action='store_true', default=None, dest='config_build_arch');
    oParser.add_argument('--build-debug', help='Build with debugging symbols and assertions', action='store_true', default=None, dest='kbuild_type=debug');
    oParser.add_argument('--build-headless', help='Build headless (without any GUI frontend)', action='store_true', dest='config_build_headless');
    # Windows-specific arguments (legacy versions, kept for backwards compatibility).
    oParser.add_argument('--disable-com', help='Disable building components which require COM', action='store_true', dest='config_disable_com');
    oParser.add_argument('--with-DDK', help='Where the WDK is to be found', action='store_true', dest='config_win_ddk_path');
    oParser.add_argument('--with-midl', help='Where midl.exe is to be found', action='store_true', dest='config_win_midl_path');
    oParser.add_argument('--with-nasm', help='Where NASM is to be found (optional)', action='store_true', dest='config_win_nasm_path');
    oParser.add_argument('--with-SDK', help='Where the Windows SDK is to be found', action='store_true', dest='config_win_sdk_path');
    oParser.add_argument('--with-SDK10', help='Where the Windows 10 SDK/WDK is to be found', action='store_true', dest='config_win_sdk10_path');
    oParser.add_argument('--with-VC-Common', help='Maybe needed for 2015 and older to locate the Common7 directory', action='store_true', dest='config_win_vc_common_path');
    oParser.add_argument('--with-VC', help='Where the Visual C++ compiler is to be found. Expecting bin, include and lib subdirs', action='store_true', dest='config_win_vc_path');
    oParser.add_argument('--with-yasm=PATH', help='Where YASM is to be found', action='store_true', dest='config_libs_path_yasm'); ## Note: Same as above in libs block.

    try:
        oArgs = oParser.parse_args();
    except argparse.ArgumentError as e:
        printError(f"Argument error: {str(e)}");
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
    g_fNoFatal = oArgs.config_nofatal;
    g_sFileLog = oArgs.config_file_log;

    # Set defaults.
    g_oEnv.set('KBUILD_TYPE', BuildType.RELEASE);
    g_oEnv.set('KBUILD_TARGET', oArgs.config_build_target if oArgs.config_build_target else g_enmHostTarget);
    g_oEnv.set('KBUILD_TARGET_ARCH', oArgs.config_build_arch if oArgs.config_build_arch else g_enmHostArch);
    g_oEnv.set('KBUILD_PATH', oArgs.config_tools_path_kbuild);
    g_oEnv.set('VBOX_OSE', '1');
    g_oEnv.set('VBOX_WITH_HARDENING', '1');
    g_oEnv.set('PATH_OUT_BASE', oArgs.config_path_out_base);

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
    print();
    print(f'Host OS / arch     : { g_sHostTarget}.{g_sHostArch}');
    print(f'Building for target: { g_oEnv["KBUILD_TARGET"] }.{ g_oEnv["KBUILD_TARGET_ARCH"] }');
    print(f'Build type         : { g_oEnv["KBUILD_TYPE"] }');
    print();

    #
    # Handle OSE building.
    #
    fOSE = g_oEnv.get('VBOX_OSE');
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
    #
    aOsTools = {
        BuildTarget.LINUX:   [ 'gcc', 'make', 'pkg-config' ],
        BuildTarget.DARWIN:  [ 'clang', 'make', 'brew' ],
        BuildTarget.WINDOWS: [ 'msbuild' ],
        BuildTarget.SOLARIS: [ 'cc', 'gmake', 'pkg-config' ]
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
    or g_fNoFatal:
        print();
        for oToolCur in aoToolsToCheck:
            oToolCur.setArgs(oArgs);
            oToolCur.performCheck();

    #
    # Perform library checks.
    #
    if g_cErrors == 0 \
    or g_fNoFatal:
        print();
        for oLibCur in aoLibsToCheck:
            oLibCur.setArgs(oArgs);
            oLibCur.performCheck();
            if oLibCur.fHave:
                oLibCur.compileAndExecute(g_oEnv['KBUILD_BUILD_TARGET'], g_oEnv['KBUILD_BUILD_TARGET_ARCH']);
    #
    # Print summary.
    #
    if g_cErrors == 0 \
    or g_fNoFatal:

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

    if g_cErrors == 0 \
    or g_fNoFatal:
        if write_autoconfig_kmk(oArgs.config_file_autoconfig, g_oEnv, g_aoLibs, g_aoTools):
            if write_env(oArgs.config_file_env, g_oEnv, g_aoLibs, g_aoTools):
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

        if g_oEnv['KBUILD_TARGET'] == BuildTarget.LINUX:
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
    if  g_fNoFatal \
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
