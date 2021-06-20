#!/bin/sh

set -e

if [ $# -lt 1 ]; then
    echo $0 {vc.zip sdk.zip target|target}
    exit 0
fi

if [ $# -eq 3 ]; then
    VC_ZIP=$(cd $(dirname $1) && pwd)/$(basename $1)
    SDK_ZIP=$(cd $(dirname $2) && pwd)/$(basename $2)
    DEST=$3
else
    DEST=$1
fi
ORIG=$(cd $(dirname $0) && pwd)

mkdir -p $DEST
cd $DEST
DEST=$(pwd)

if [ -n "$VC_ZIP" ]; then
    unzip $VC_ZIP
fi
test -e "VC" && mv VC vc
test -e "vc/Tools" && mv vc/Tools vc/tools
test -e "vc/tools/MSVC" && mv vc/tools/MSVC vc/tools/msvc
if [ -d kits/10 ]; then
    cd kits/10
else
    mkdir kits
    cd kits
    unzip $SDK_ZIP
    cd 10
fi
test -e "Lib" && mv Lib lib
test -e "Include" && mv Include include
cd ../..
SDKVER=$(basename $(echo kits/10/include/* | awk '{print $NF}'))
MSVCVER=$(basename $(echo vc/tools/msvc/* | awk '{print $1}'))

# Fix casing of includes and libs.
# Generates a vfsoverlay mapping file for clang and lld to use.
# Note that this requires a custom build of lld for now.

# Generates VFS overlay for case insensitivity.
gen_winsdk_vfs_overlay(){
    local VFS="vfs.yaml"
    cat >"$VFS"<<EOF
version: 0
case-sensitive: false
roots:
EOF

    # skip cppwinrt
    local HDIRS=`find $PWD/kits/10/lib/$SDKVER/{ucrt,um} $PWD/kits/10/include/$SDKVER/{shared,ucrt,um,winrt} -type d`
    for d in $HDIRS; do
        local hs=`find "$d" -maxdepth 1 -type f -iname "*.h" -iname "*.lib"`
        [ -n "$hs" ] || continue
        cat >> "$VFS" <<EOF
  - name: $d
    type: directory
    contents:
EOF
        for h in $hs; do
            cat >> "$VFS" <<EOF
      - name: ${h##*/}
        type: file
        external-contents: "$h"
EOF
        done
    done
}

gen_winsdk_vfs_overlay


cat $ORIG/wrappers/msvcenv.sh | sed 's/MSVCVER=.*/MSVCVER='$MSVCVER/ | sed 's/SDKVER=.*/SDKVER='$SDKVER/ | sed 's,BASE=.*,BASE='$DEST, > msvcenv.sh
for arch in x86 x64 arm arm64; do
    mkdir -p bin/$arch
    cp $ORIG/wrappers/* bin/$arch
    # If cache lost the +w bit, restore it.
    chmod +w bin/$arch/msvcenv.sh
    cat msvcenv.sh | sed 's/ARCH=.*/ARCH='$arch/ > bin/$arch/msvcenv.sh
done
rm msvcenv.sh
