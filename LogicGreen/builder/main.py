# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from os.path import join
from time import sleep

from SCons.Script import (ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild,
                          Builder, Default, DefaultEnvironment)

from platformio.util import get_serial_ports

env = DefaultEnvironment()

env.Replace(
    AR="avr-gcc-ar",
    AS="avr-as",
    CC="avr-gcc",
    GDB="avr-gdb",
    CXX="avr-g++",
    OBJCOPY="avr-objcopy",
    RANLIB="avr-gcc-ranlib",
    SIZETOOL="avr-size",

    ARFLAGS=["rc"],

    SIZEPROGREGEXP=r"^(?:\.text|\.data|\.bootloader)\s+(\d+).*",
    SIZEDATAREGEXP=r"^(?:\.data|\.bss|\.noinit)\s+(\d+).*",
    SIZECHECKCMD="$SIZETOOL -A -d $SOURCES",
    SIZEPRINTCMD='$SIZETOOL --mcu=$BOARD_MCU -C -d $SOURCES',

    PROGSUFFIX=".elf"
)

env.Append(
    BUILDERS=dict(
        ElfToEep=Builder(
            action=env.VerboseAction(" ".join([
                "$OBJCOPY",
                "-O",
                "ihex",
                "-j",
                ".eeprom",
                '--set-section-flags=.eeprom="alloc,load"',
                "--no-change-warnings",
                "--change-section-lma",
                ".eeprom=0",
                "$SOURCES",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".eep"
        ),

        ElfToHex=Builder(
            action=env.VerboseAction(" ".join([
                "$OBJCOPY",
                "-O",
                "ihex",
                "-R",
                ".eeprom",
                "$SOURCES",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".hex"
        )
    )
)

# Allow user to override via pre:script
if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

#
# Target: Build executable and linkable firmware
#

target_elf = None
if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.hex")
else:
    target_elf = env.BuildProgram()
    target_firm = env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), target_elf)

AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog = env.Alias("buildprog", target_firm, target_firm)

#
# Target: Print binary size
#

target_size = env.Alias(
    "size", target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE"))
AlwaysBuild(target_size)

# Set clock

board_clock_source = env.subst("$BOARD_CLOCK_SOURCE")
env.Replace(
        BOARD_CLOCK_SOURCE="$BOARD_CLOCK_SOURCE"
    )

#
# Target: Upload by default .hex file
#

upload_protocol = env.subst("$UPLOAD_PROTOCOL")

env.Replace(
        UPLOADER="avrdude",
        UPLOADERFLAGS=[
            "-p", "$BOARD_MCU",
            "-C",
            join(env.PioPlatform().get_package_dir("tool-avrdude") or "",
                 "avrdude.conf"),
            "-c", "$UPLOAD_PROTOCOL"
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS -U flash:w:$SOURCES:i',
        UPLOADEEPCMD='$UPLOADER $UPLOADERFLAGS -U eeprom:w:$SOURCES:i'
)


upload_actions = [
        env.VerboseAction(BeforeUpload, "Looking for upload port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE $UPLOADCMD")
]

AlwaysBuild(env.Alias("upload", target_firm, upload_actions))

#
# Target: Upload EEPROM data (from EEMEM directive)
#
target_uploadeep = env.Alias(
    "uploadeep",
    join("$BUILD_DIR", "${PROGNAME}.eep")
    if "nobuild" in COMMAND_LINE_TARGETS else env.ElfToEep(target_elf), [
        env.VerboseAction(BeforeUpload, "Looking for upload port..."),
        env.VerboseAction("$UPLOADEEPCMD", "Uploading $SOURCE")
    ])
AlwaysBuild(target_uploadeep)

#
# Target: Upload firmware using external programmer
#

target_program = env.Alias(
    "program", target_firm,
    env.VerboseAction("$UPLOADCMD", "Programming $SOURCE"))
AlwaysBuild(target_program)

#
# Setup default targets
#

Default([target_buildprog, target_size])