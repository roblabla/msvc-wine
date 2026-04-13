import argparse
import base64
import json
from pathlib import Path
import vsdownload
import sys
import urllib.request
import shutil
import subprocess

def downloadInstaller(cache):
    feed_url = 'https://aka.ms/vs/installer/latest/feed'
    print("Fetching %s" % (feed_url))
    manifest = json.loads(urllib.request.urlopen(feed_url).read())

    urllib.request.urlretrieve(manifest['installerUrl'], cache + '/vs_installer.opc')
    urllib.request.urlretrieve(manifest['bootstrapperUrl'], cache + '/vs_Setup.exe')
    shutil.copyfile(cache + '/vs_Setup.exe', cache + '/vs_buildtools.exe')

    # TODO: Check how vs_layout.exe actually generates vs_installer.version.json
    with open(cache + "/vs_installer.version.json", "w") as f:
        json.dump({
            "version": manifest["setupPackageVersion"],
            "branch": "release",
            "name": "vs-xsetup",
            "installerVersion": manifest["installerVersion"]
        }, f)


def writeCertificates(cache, manifest):
    certdir = cache + "/certificates"
    vsdownload.makedirs(certdir)

    cert = base64.b64decode(manifest['signature']['keyInfo']['x509Data'][0])
    with open(certdir + "/manifestRootCertificate.cer", "wb") as f:
        f.write(cert)

    cert = base64.b64decode(manifest['signature']['counterSign']['x509Data'][0])
    with open(certdir + "/manifestCounterSignRootCertificate.cer", "wb") as f:
        f.write(cert)

    # TODO: Figure out where this cert comes from
    urllib.request.urlretrieve('https://www.microsoft.com/pki/certs/MicRooCerAut_2010-06-23.crt', certdir+ '/vs_installer_opc.RootCertificate.cer')


def downloadLayout(s3_endpoint, s3_bucket, s3_prefix, cache, major, wanted_packages):
    if not s3_prefix.endswith("/"):
        args.s3_prefix += "/"

    parser = vsdownload.getArgsParser()
    args = parser.parse_args(["--major", str(major), "--only-host", "no"] + wanted_packages)
    vsdownload.lowercaseIgnores(args)

    # Check if we already have a channel file. If so, use it.
    existing_url = f"{s3_endpoint}/{s3_bucket}/{s3_prefix}ChannelManifest.json"
    try:
        print("Using existing channel from url", existing_url)
        channel_raw = urllib.request.urlopen(existing_url).read()
    except urllib.error.HTTPError:
        print("Downloading channel from MSVC")
        channel_raw = vsdownload.getRawChannel(args)

    channel = json.loads(channel_raw)
    print("Got toplevel manifest for %s" % (channel["info"]["productDisplayVersion"]))
    for item in channel["channelItems"]:
        if "type" in item and item["type"] == "Manifest":
            args.manifest = item["payloads"][0]["url"]
    if args.manifest == None:
        print("Unable to find an intaller manifest!")
        sys.exit(1)

    manifest_raw = vsdownload.getRawManifest(args)
    manifest = json.loads(manifest_raw)
    print("Loaded installer manifest for %s" % (manifest["info"]["productDisplayVersion"]))
    packages = vsdownload.getPackages(manifest, args.host_arch)
    vsdownload.setPackageSelection(args, packages)
    selected = vsdownload.getSelectedPackages(packages, args)
    vsdownload.downloadPackages(selected, cache, allowHashMismatch=args.only_download)

    # Now, complete the layout.
    with open(cache + "/ChannelManifest.json", "wb") as f:
        f.write(channel_raw)
    with open(cache + "/Catalog.json", "wb") as f:
        f.write(manifest_raw)
    with open(cache + "/Response.json", "w") as f:
        json.dump({
            "installChannelUri": ".\\ChannelManifest.json",
            "channelUri": "https://aka.ms/vs/16/release/channel",
            "installCatalogUri": ".\\Catalog.json",
            "channelId": "VisualStudio.16.Release",
            "productId": "Microsoft.VisualStudio.Product.BuildTools",
            "add": wanted_packages,
            "addProductLang":[
                "en-US"
            ]
        }, f)

    writeCertificates(cache, manifest)
    downloadInstaller(cache)


def uploadToS3(s3_endpoint, s3_bucket, s3_prefix, cache):
    if not s3_prefix.endswith("/"):
        s3_prefix += "/"

    cache = Path(cache)
    # Get all files on s3.
    endpoint_args = []
    if s3_endpoint:
        endpoint_args = ["--endpoint-url", s3_endpoint]
    res = subprocess.run(["aws"] + endpoint_args + ["s3api", "list-objects", "--no-cli-pager", "--bucket", s3_bucket, "--prefix", s3_prefix], capture_output=True, encoding='utf8', check=True)
    raw_data = json.loads(res.stdout)
    data = { v['Key'].removeprefix(s3_prefix): v for v in raw_data.get('Contents', []) }

    for file in (x for x in cache.glob("**/*") if x.is_file()):
        relfile = str(file.relative_to(cache))

        if relfile in data:
            if file.stat().st_size == data[relfile]['Size']:
                print("Skipping already uploaded file", relfile)
                continue

        suffix_to_mime = {
            '.cab': 'application/vnd.ms-cab-compressed',
            '.cer': 'application/octet-stream',
            '.exe': 'application/octet-stream',
            '.json': 'application/json',
            '.msi': 'application/octet-stream',
            '.msu': 'application/octet-stream',
            '.msp': 'application/octet-stream',
            '.nupkg': 'application/octet-stream',
            '.opc': 'application/octet-stream',
            '.ps1': 'application/postscript',
            '.vsix': 'application/octet-stream',
            '.xml': 'text/xml',
            '.zip': 'application/x-zip-compressed',
        }
        if file.suffix in suffix_to_mime:
            content_type = suffix_to_mime[file.suffix]
        else:
            print(f"====== Unknown type for file {file}")
            content_type = 'application/octet-stream'
        print(f"Uploading {file}")
        overwrite = ["--no-overwrite"]
        overwrite = []
        if file.name in ["Response.json", "ChannelManifest.json", "Catalog.json"]:
            overwrite = []

        subprocess.run(["aws"] + endpoint_args + ["s3", "cp"] + overwrite + ["--content-type", content_type, str(file), f"s3://{s3_bucket}/{s3_prefix}{relfile}"], check=True)


def main():
    parser = argparse.ArgumentParser(description = "Download and install Visual Studio")
    parser.add_argument('--s3-endpoint')
    parser.add_argument('--s3-bucket', required=True)
    parser.add_argument('--s3-prefix', required=True)
    args = parser.parse_args()

    if not args.s3_prefix.endswith("/"):
        args.s3_prefix += "/"

    vs2019_prefix = args.s3_prefix + "vs2019/"
    vs2022_prefix = args.s3_prefix + "vs2022/"

    # First, download the manifest if it already exists.

    #downloadLayout(args.s3_endpoint, args.s3_bucket, vs2019_prefix, "cache_vs2019", 16, [
    #    "Microsoft.VisualStudio.Product.BuildTools",
    #    "Microsoft.VisualStudio.Component.VC.Runtimes.ARM64.Spectre",
    #    "Microsoft.VisualStudio.Component.VC.Runtimes.x86.x64.Spectre",
    #    "Microsoft.VisualStudio.Component.VC.Tools.ARM64",
    #    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
    #    "Microsoft.VisualStudio.Workload.MSBuildTools",
    #    "Microsoft.VisualStudio.Workload.VCTools",
    #    "Microsoft.VisualStudio.Component.Windows10SDK.19041",
    #])
    downloadLayout(args.s3_endpoint, args.s3_bucket, vs2022_prefix, "cache_vs2022", 17, [
        "Microsoft.VisualStudio.Product.BuildTools",
        "Microsoft.VisualStudio.Component.VC.Runtimes.ARM64.Spectre",
        "Microsoft.VisualStudio.Component.VC.Runtimes.x86.x64.Spectre",
        "Microsoft.VisualStudio.Component.VC.Tools.ARM64",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
        "Microsoft.VisualStudio.Workload.MSBuildTools",
        "Microsoft.VisualStudio.Workload.VCTools",
        "Microsoft.VisualStudio.Component.Windows11SDK.26100",
        "Component.Microsoft.Windows.DriverKit",
    ])
    #uploadToS3(args.s3_endpoint, args.s3_bucket, vs2019_prefix, "cache_vs2019")
    uploadToS3(args.s3_endpoint, args.s3_bucket, vs2022_prefix, "cache_vs2022")

if __name__ == '__main__':
    main()
