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
# For includes, the easiest way is to generate a vfsoverlay mapping file for
# clang to use.
# For libs, there's no easy solution... We'll just symlink lower.lib and UPPER.lib
# and hope that it's enough. Eventually, the ideal solution would be for LLD to
# gain the ability to use a vfsoverlay as well.

# TODO: Includes
#$ORIG/lowercase kits/10/include/$SDKVER/um
#$ORIG/lowercase kits/10/include/$SDKVER/shared
#$ORIG/fixinclude kits/10/include/$SDKVER/um
#$ORIG/fixinclude kits/10/include/$SDKVER/shared

# Libs
fix_libs () {
    path="$1"
    for f in $path/*; do
        if [ -h $f ]; then
            continue
        elif [ -d $f ]; then
            fix_libs $f
        elif [ -f $f ]; then
            dirname=$(dirname "$f")
            basename=$(basename "$f")
            filename="${basename%.*}"
            extension="${basename##*.}"

            filename_l=$(echo "$filename" | tr '[:upper:]' '[:lower:]')
            filename_u=$(echo "$filename" | tr '[:lower:]' '[:upper:]')

            extension_l=$(echo "$extension" | tr '[:upper:]' '[:lower:]')

            basename1=$filename_l.$extension_l
            basename2=$filename_u.$extension_l

            if [ $basename != $basename1 ]; then
                ln -s $basename $dirname/$basename1
            fi
            if [ $basename != $basename2 ]; then
                ln -s $basename $dirname/$basename2
            fi
        fi
    done
}

for arch in x86 x64 arm arm64; do
    fix_libs "kits/10/lib/$SDKVER/um/$arch"
    fix_libs "vc/tools/msvc/$MSVCVER/lib/$arch"
done

cat $ORIG/wrappers/msvcenv.sh | sed 's/MSVCVER=.*/MSVCVER='$MSVCVER/ | sed 's/SDKVER=.*/SDKVER='$SDKVER/ | sed 's,BASE=.*,BASE='$DEST, > msvcenv.sh
for arch in x86 x64 arm arm64; do
    mkdir -p bin/$arch
    cp $ORIG/wrappers/* bin/$arch
    # If cache lost the +w bit, restore it.
    chmod +w bin/$arch/msvcenv.sh
    cat msvcenv.sh | sed 's/ARCH=.*/ARCH='$arch/ > bin/$arch/msvcenv.sh
done
rm msvcenv.sh
