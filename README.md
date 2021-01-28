Cross compilation with MSVC on Linux
====================================

This is a reproducible Dockerfile for cross compiling with MSVC on Linux,
usable as base image for CI style setups.

This downloads and unpacks the necessary Visual Studio components using
the same installer manifests as Visual Studio 2017/2019's installer
uses. Downloading and installing it requires accepting the license,
available at https://go.microsoft.com/fwlink/?LinkId=2086102 for the
currently latest version.

As Visual Studio isn't redistributable, the resulting docker image isn't
either.

Build the docker image like this:

    docker build .

After building the docker image, there are 4 directories with tools,
in `/opt/msvc/bin/<arch>`, for all architectures out of `x86`,
`x64`, `arm` and `arm64`, that should be added to the PATH before building
with it.

The installer scripts also work fine without docker; just run the following two commands:

    ./vsdownload.py --dest <dir>
    ./install.sh <dir>

The unpacking requires recent versions of msitools (0.98) and libgcab
(1.2); sufficiently new versions are available in e.g. Ubuntu 19.04.

--------

## Setting up this toolchain for easy cross-compilation in Rust

With this toolchain, cross-compiling rust code has never been easier. Here's
what you need to do to get setup:

1. Install this toolchain, e.g. `./vsdownload.py --dest /opt/msvc &&
   ./install.sh /opt/msvc`. You can install it anywhere.
2. Install `clang`, `llvm-lib` and `llvm-rc`:
    - `clang` will be used to compile any C dependencies you may have with the
      `cc` crate. Windows officially supports building `msvc` binaries in clang
      since 2019, so it should handle sdk headers and libraries just fine.
   - `llvm-lib` will be used to statically link code when using the `cc` crate.
     It generates `.lib` files compatible with the windows linker.
   - `llvm-rc` will be used to compile resource files (used to add manifests and
     icons to an executable) with the `embed-resource` crate. This will also
     generate `.lib` files.
3. In your `.cargo/config`, set the following variables:

    ```toml
    [target.x86_64-pc-windows-msvc]
    linker = "/opt/msvc/bin/x64/lld-link"

    [target.i586-pc-windows-msvc]
    linker = "/opt/msvc/bin/x86/lld-link"

    [target.i686-pc-windows-msvc]
    linker = "/opt/msvc/bin/x86/lld-link"

    [target.aarch64-pc-windows-msvc]
    linker = "/opt/msvc/bin/arm64/lld-link"
    ```

    Note: `lld-link` is simply a wrapper script around `rust-lld`, allowing it
    to find the windows libraries to link against.

4. In your shell, set the following env variables:

    ```
    export CC_x86_64_pc_windows_msvc=/opt/msvc/bin/x64/clang-cl
    export AR_x86_64_pc_windows_msvc=llvm-lib
    export RC_x86_64_pc_windows_msvc=llvm-rc
    export CC_i686_pc_windows_msvc=/opt/msvc/bin/x86/clang-cl
    export AR_i686_pc_windows_msvc=llvm-lib
    export RC_i686_pc_windows_msvc=llvm-rc
    export CC_i586_pc_windows_msvc=/opt/msvc/bin/x86/clang-cl
    export AR_i586_pc_windows_msvc=llvm-lib
    export RC_i586_pc_windows_msvc=llvm-rc
    export CC_aarch64_pc_windows_msvc=/opt/msvc/bin/x86/clang-cl
    export AR_aarch64_pc_windows_msvc=llvm-lib
    export RC_aarch64_pc_windows_msvc=llvm-rc
    ```

Congratulations, you're now all set!