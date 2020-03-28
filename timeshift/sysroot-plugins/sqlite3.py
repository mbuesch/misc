# Copyright (c) 2020, Michael Buesch
# Copyright (c) 2019, Riverbank Computing Limited
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


import os

from pyqtdeploy.sysroot import ComponentBase, ComponentOption


class sqlite3Component(ComponentBase):
    """ The sqlite3 component. """

    # The component options.
    options = [
        ComponentOption('source', required=True,
                help="The archive containing the source code."),
    ]

    def build(self, sysroot):
        """ Build zlib for the target. """

        archive = sysroot.find_file(self.source)
        sysroot.unpack_archive(archive)

        if sysroot.target_platform_name == 'android':
            # Configure the environment.
            original_path = sysroot.add_to_path(sysroot.android_toolchain_bin)
            os.environ['CROSS_PREFIX'] = sysroot.android_toolchain_prefix
            os.environ['CC'] = sysroot.android_toolchain_cc

            cflags = sysroot.android_toolchain_cflags

            # It isn't clear why this is needed, possibly a clang bug.
            if sysroot.target_arch_name == 'android-32' and sysroot.android_ndk_version >= (16, 0, 0):
                cflags.append('-fPIC')

            os.environ['CFLAGS'] = ' '.join(cflags)

            sysroot.run('./configure',
                    "--host=arm-linux",
                    '--prefix=' + sysroot.sysroot_dir)
            sysroot.run(sysroot.host_make,
                    'AR=' + sysroot.android_toolchain_prefix + 'ar cqs',
                    'install')

            del os.environ['CROSS_PREFIX']
            del os.environ['CC']
            del os.environ['CFLAGS']
            os.environ['PATH'] = original_path

        else:
            if sysroot.target_platform_name == 'ios':
                # Note that this doesn't create a library that can be used with
                # an x86-based simulator.
                os.environ['CFLAGS'] = '-fembed-bitcode -O3 -arch arm64 -isysroot ' + sysroot.apple_sdk

            sysroot.run('./configure',
                    "--host=arm-linux",
                    '--prefix=' + sysroot.sysroot_dir)
            sysroot.run(sysroot.host_make)
            sysroot.run(sysroot.host_make, 'install')

            if sysroot.target_platform_name == 'ios':
                del os.environ['CFLAGS']

    def configure(self, sysroot):
        """ Complete the configuration of the component. """

        sysroot.verify_source(self.source)
