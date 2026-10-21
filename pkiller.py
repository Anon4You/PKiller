import os
import sys
import shutil
import subprocess
import re
import threading
import time
import argparse
import glob
import zipfile
from termcolor import colored

stop_spinner = False
script_name = os.path.basename(sys.argv[0])

def show_banner():
    try:
        result = subprocess.run(['asciibanner', '-f', 'ANSI Shadow', 'PKiller'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(colored(result.stdout, "green"))
        else:
            print(colored("PKiller", "green", attrs=['bold']))
    except:
        print(colored("PKiller", "green", attrs=['bold']))
    
    print(colored("Pairip Licence Check Remover", "white"))
    print(colored("Author : Alienkrishn | GitHub : Anon4You", "white", attrs=['bold']))
    print(colored("=" * 50, "green"))

def show_spinner():
    spinner = ['|', '/', '-', '\\']
    i = 0
    while not stop_spinner:
        sys.stdout.write(f'\r{colored(spinner[i], "green")} Processing...')
        sys.stdout.flush()
        time.sleep(0.1)
        i = (i + 1) % 4

def start_spinner():
    global stop_spinner
    stop_spinner = False
    t = threading.Thread(target=show_spinner)
    t.daemon = True
    t.start()
    return t

def stop_spinner_thread():
    global stop_spinner
    stop_spinner = True
    time.sleep(0.2)
    sys.stdout.write('\r' + ' ' * 30 + '\r')
    sys.stdout.flush()

def run_with_spinner(cmd, success_msg, error_msg):
    spinner_thread = start_spinner()
    result = subprocess.run(cmd, capture_output=True, text=True)
    stop_spinner_thread()
    if result.returncode != 0:
        print(colored(f"[-] {error_msg}: {result.stderr[:100]}", "red"))
        return False
    print(colored(f"[+] {success_msg}", "green"))
    return True

def check_tools():
    print(colored("Checking dependencies...", "white"))
    tools = {
        'apkeditor': 'APK Editor',
        'apksigner': 'APK Signer',
        'keytool': 'Java Keytool'
    }
    
    all_found = True
    for tool, name in tools.items():
        try:
            subprocess.run([tool, '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(colored(f"  [+] {name} found", "green"))
        except FileNotFoundError:
            print(colored(f"  [-] {name} not found", "red"))
            all_found = False
    
    return all_found

def decode_apk(apk_path, output_dir):
    print(colored("\n[1/5] Decoding APK...", "white"))
    if not os.path.exists(apk_path):
        print(colored(f"[-] File not found: {apk_path}", "red"))
        return False
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    cmd = ['apkeditor', 'd', '-i', apk_path, '-o', output_dir]
    return run_with_spinner(cmd, "APK decoded", "Decode failed")

def get_pairip_application_super(decoded_dir):
    """If <application android:name> points at a pairip wrapper class, find the
    real app Application class (the wrapper's .super) before pairip smali is
    removed. Returns (old_name, real_app_dotted) or None."""
    manifest_path = os.path.join(decoded_dir, 'AndroidManifest.xml')
    if not os.path.exists(manifest_path):
        return None
    with open(manifest_path, 'r', encoding='utf-8') as f:
        content = f.read()
    app_tag = re.search(r'<application\b(.*?)>', content, re.DOTALL)
    if not app_tag:
        return None
    name_m = re.search(r'android:name="([^"]*)"', app_tag.group(1))
    if not name_m:
        return None
    name = name_m.group(1)
    if 'pairip' not in name.lower():
        return None

    def find_super(class_name):
        smali_rel = class_name.replace('.', '/') + '.smali'
        candidates = (glob.glob(os.path.join(decoded_dir, 'smali*', smali_rel)) +
                      glob.glob(os.path.join(decoded_dir, 'smali', 'classes*', smali_rel)))
        for candidate in sorted(candidates):
            with open(candidate, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('.super '):
                        return line[len('.super '):].strip()
        return None

    current = name
    for _ in range(6):
        super_sig = find_super(current)
        if super_sig is None or not (super_sig.startswith('L') and super_sig.endswith(';')):
            print(colored(f"[*] Could not resolve real Application class for {current}", "white"))
            return None
        internal = super_sig[1:-1]
        if 'pairip' not in internal.lower():
            dotted = internal.replace('/', '.')
            print(colored(f"[*] Pairip Application wrapper detected: {name} -> {dotted}", "white"))
            return name, dotted
        current = internal
    print(colored(f"[*] Could not resolve real Application class for {name}", "white"))
    return None

def remove_pairip_smali(decoded_dir):
    print(colored("\n[2/5] Removing PairIP files...", "white"))
    found = False
    for scan_dir in sorted(_smali_dirs(decoded_dir)):
        pairip_path = os.path.join(scan_dir, "com/pairip")
        if os.path.exists(pairip_path):
            shutil.rmtree(pairip_path)
            print(colored(f"  [+] Removed PairIP smali directory ({os.path.relpath(scan_dir, decoded_dir)})", "green"))
            found = True
        for root, dirs, files in os.walk(scan_dir):
            for dir_name in list(dirs):
                if 'pairip' in dir_name.lower() or 'license' in dir_name.lower():
                    dir_path = os.path.join(root, dir_name)
                    shutil.rmtree(dir_path)
                    dirs.remove(dir_name)
                    found = True
                    print(colored(f"  [+] Removed: {dir_name}", "green"))
    if not found:
        print(colored("  [*] No PairIP directories found", "white"))
    return True

def _smali_dirs(decoded_dir):
    """All code directories: smali/classes*, plus legacy smali/ layouts."""
    dirs = []
    for smali_root in sorted(glob.glob(os.path.join(decoded_dir, 'smali*'))):
        classes_dirs = sorted(glob.glob(os.path.join(smali_root, 'classes*')))
        if classes_dirs:
            dirs.extend(classes_dirs)
        else:
            dirs.append(smali_root)
    return dirs


def clean_manifest(decoded_dir, pairip_app=None):
    print(colored("\n[3/5] Cleaning AndroidManifest.xml...", "white"))
    manifest_path = os.path.join(decoded_dir, "AndroidManifest.xml")
    if not os.path.exists(manifest_path):
        print(colored("[-] Manifest not found", "red"))
        return False
    
    spinner_thread = start_spinner()
    with open(manifest_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    patterns = [
        r'<activity\s+[^>]*?android:name="[^"]*pairip[^"]*LicenseActivity"[^>]*/>\s*',
        r'<provider\s+[^>]*?android:name="[^"]*pairip[^"]*LicenseContentProvider"[^>]*/>\s*',
        r'<uses-permission\s+[^>]*?android:name="com\.android\.vending\.CHECK_LICENSE"[^>]*/>\s*'
    ]
    
    removed_count = 0
    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        removed_count += len(matches)
        content = re.sub(pattern, '', content, flags=re.IGNORECASE)
    
    with open(manifest_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    if pairip_app:
        old_name, new_name = pairip_app
        replaced = len(re.findall(rf'android:name="{re.escape(old_name)}"', content))
        if replaced:
            content = re.sub(rf'android:name="{re.escape(old_name)}"',
                             f'android:name="{new_name}"', content)
            with open(manifest_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(colored(f"  [+] Restored real Application class: {new_name}", "green"))
        else:
            print(colored(f"[*] Pairip application class {old_name} not found in manifest", "white"))
    
    stop_spinner_thread()
    print(colored(f"  [+] Removed {removed_count} PairIP entries", "green"))
    return True

def rebuild_apk(decoded_dir, output_apk):
    print(colored("\n[4/5] Rebuilding APK...", "white"))
    if os.path.exists(output_apk):
        os.remove(output_apk)
    cmd = ['apkeditor', 'b', '-i', decoded_dir, '-o', output_apk]
    return run_with_spinner(cmd, "APK rebuilt", "Rebuild failed")

def create_keystore(keystore_path):
    print(colored("Creating keystore...", "white"))
    keystore_dir = os.path.dirname(keystore_path)
    os.makedirs(keystore_dir, exist_ok=True)
    
    keytool_cmd = [
        'keytool', '-genkey', '-v',
        '-keystore', keystore_path,
        '-alias', 'PKiller',
        '-keyalg', 'RSA',
        '-keysize', '2048',
        '-validity', '10000',
        '-storepass', 'pkiller',
        '-keypass', 'pkiller',
        '-dname', 'CN=PKiller, OU=PKiller, O=PKiller, L=Unknown, ST=Unknown, C=IN'
    ]
    
    return run_with_spinner(keytool_cmd, "Keystore created", "Failed to create keystore")

def get_keystore():
    return os.path.join(os.environ.get('PREFIX', '/data/data/com.termux/files/usr'), 
                        'share', 'PKiller', 'key', 'PKiller.keystore')

def signed_name(apk_path):
    root, _ = os.path.splitext(apk_path)
    return root + '_signed.apk'

def apksigner_cmd(keystore_path, signed_apk, apk_path):
    return [
        'apksigner', 'sign',
        '--ks', keystore_path,
        '--ks-pass', 'pass:pkiller',
        '--ks-key-alias', 'PKiller',
        '--key-pass', 'pass:pkiller',
        '--out', signed_apk,
        apk_path
    ]

def sign_apk(apk_path):
    print(colored("\n[5/5] Signing APK...", "white"))
    
    keystore_path = get_keystore()
    
    if not os.path.exists(keystore_path):
        if not create_keystore(keystore_path):
            print(colored("[-] Cannot proceed without keystore", "red"))
            return None
    
    signed_apk = signed_name(apk_path)
    cmd = apksigner_cmd(keystore_path, signed_apk, apk_path)
    
    if run_with_spinner(cmd, "APK signed", "Sign failed"):
        return signed_apk
    return None

def sign_splits(splits):
    print(colored("\nSigning bundle splits...", "white"))
    for split in splits:
        split_name = os.path.basename(split)
        cmd = apksigner_cmd(get_keystore(), signed_name(split), split)
        if not run_with_spinner(cmd, f"Signed {split_name}", f"Failed to sign {split_name}"):
            return False
    return True

def extract_bundle(bundle_path, output_dir):
    print(colored("\nExtracting bundle...", "white"))
    if not os.path.exists(bundle_path):
        print(colored(f"[-] File not found: {bundle_path}", "red"))
        return None, []
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        bundle_root = os.path.realpath(output_dir)
        with zipfile.ZipFile(bundle_path) as z:
            for name in z.namelist():
                dest = os.path.realpath(os.path.join(output_dir, name))
                if dest != bundle_root and not dest.startswith(bundle_root + os.sep):
                    raise zipfile.BadZipFile(f"Unsafe path in bundle: {name}")
            z.extractall(output_dir)
    except zipfile.BadZipFile as e:
        print(colored(f"[-] Invalid bundle: {e}", "red"))
        shutil.rmtree(output_dir, ignore_errors=True)
        return None, []
    
    apk_files = sorted(glob.glob(os.path.join(output_dir, '**', '*.apk'), recursive=True))
    if not apk_files:
        print(colored("[-] No APK files found inside bundle", "red"))
        return None, []
    
    base_apk = next((p for p in apk_files if os.path.basename(p).lower() == 'base.apk'), None)
    if base_apk:
        splits = [p for p in apk_files if p != base_apk]
        return base_apk, splits
    
    apk_files.sort(key=os.path.getsize, reverse=True)
    base_apk = apk_files[0]
    print(colored(f"[*] No base.apk found, using largest APK as base: "
                  f"{os.path.basename(base_apk)}", "white"))
    return base_apk, apk_files[1:]

def repack_bundle(bundle_dir, base_apk, base_signed, output_path):
    print(colored("\nRepacking bundle...", "white"))
    if os.path.exists(output_path):
        os.remove(output_path)
    
    apk_files = sorted(glob.glob(os.path.join(bundle_dir, '**', '*.apk'), recursive=True))
    if not apk_files:
        print(colored("[-] No APK files found in bundle", "red"))
        return False
    
    spinner_thread = start_spinner()
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for apk in apk_files:
                arcname = os.path.relpath(apk, bundle_dir).replace(os.sep, '/')
                if apk == base_apk:
                    zout.write(base_signed, arcname)
                    continue
                if arcname.endswith('_signed.apk'):
                    continue
                signed = signed_name(apk)
                zout.write(signed if os.path.exists(signed) else apk, arcname)
    except Exception as e:
        stop_spinner_thread()
        print(colored(f"[-] Repack failed: {str(e)}", "red"))
        return False
    stop_spinner_thread()
    print(colored("[+] Bundle repacked", "green"))
    return True

def cleanup_files(output_apk=None):
    print(colored("\nCleaning up...", "white"))
    
    temp_files = glob.glob('*.idsig')
    for file in temp_files:
        try:
            os.remove(file)
        except:
            pass
    
    if os.path.exists('decoded_temp'):
        shutil.rmtree('decoded_temp')
    
    if os.path.exists('bundle_temp'):
        shutil.rmtree('bundle_temp')
    
    temp_apk = os.path.join(os.getcwd(), "temp_rebuilt.apk")
    if os.path.exists(temp_apk) and (not output_apk or temp_apk != output_apk):
        os.remove(temp_apk)
    
    temp_signed = os.path.join(os.getcwd(), "temp_rebuilt_signed.apk")
    if os.path.exists(temp_signed) and (not output_apk or temp_signed != output_apk):
        os.remove(temp_signed)

def main():
    show_banner()
    
    parser = argparse.ArgumentParser(description='Remove PairIP license from APK / .apks bundle', 
                                   add_help=False)
    parser.add_argument('apk_path', help='Path to the APK file', nargs='?')
    parser.add_argument('-o', '--output', help='Output APK filename')
    parser.add_argument('-h', '--help', action='store_true', help='Show help')
    
    args = parser.parse_args()
    
    if args.help or not args.apk_path:
        print(colored("Usage:", "white"))
        print(colored(f"  {script_name} <apk_file | apks_bundle> [-o output]", "green"))
        print(colored("\nExamples:", "white"))
        print(colored(f"  {script_name} myapp.apk", "green"))
        print(colored(f"  {script_name} bundle.apks", "green"))
        print(colored(f"  {script_name} myapp.apk -o patched_app.apk", "green"))
        print(colored(f"  {script_name} myapp.apk --output custom_name.apk", "green"))
        print(colored("\nDefault output: <original_name>_pairip_killed.apk "
                      "(or .apks for bundles)", "cyan"))
        sys.exit(0)
    
    input_apk = args.apk_path
    is_bundle = input_apk.lower().endswith('.apks')
    
    if not os.path.exists(input_apk):
        print(colored(f"\n[-] File not found: {input_apk}", "red"))
        sys.exit(1)
    
    if not check_tools():
        sys.exit(1)
    
    # Determine output filename
    output_ext = '.apks' if is_bundle else '.apk'
    if args.output:
        output_apk = args.output
        # Ensure proper extension
        if not output_apk.lower().endswith(output_ext):
            output_apk += output_ext
        output_apk = os.path.join(os.getcwd(), output_apk)
    else:
        base_name = os.path.splitext(os.path.basename(input_apk))[0]
        output_apk = os.path.join(os.getcwd(), f"{base_name}_pairip_killed{output_ext}")
    
    bundle_dir = os.path.join(os.getcwd(), "bundle_temp")
    decoded_dir = "decoded_temp"
    
    try:
        if is_bundle:
            base_apk, splits = extract_bundle(input_apk, bundle_dir)
            if not base_apk:
                cleanup_files()
                sys.exit(1)
            target_apk = base_apk
        else:
            target_apk = input_apk
        
        if not decode_apk(target_apk, decoded_dir):
            sys.exit(1)
        
        pairip_app = get_pairip_application_super(decoded_dir)
        remove_pairip_smali(decoded_dir)
        clean_manifest(decoded_dir, pairip_app)
        
        temp_apk = os.path.join(os.getcwd(), "temp_rebuilt.apk")
        if not rebuild_apk(decoded_dir, temp_apk):
            sys.exit(1)
        
        signed_apk = sign_apk(temp_apk)
        
        if not signed_apk:
            print(colored("[-] Failed to sign APK", "red"))
            cleanup_files()
            sys.exit(1)
        
        if is_bundle:
            if splits and not sign_splits(splits):
                print(colored("[-] Failed to sign bundle splits", "red"))
                cleanup_files()
                sys.exit(1)
            if not repack_bundle(bundle_dir, base_apk, signed_apk, output_apk):
                cleanup_files()
                sys.exit(1)
        else:
            os.rename(signed_apk, output_apk)
        
        cleanup_files(output_apk)
        
        print(colored(f"\n" + "=" * 50, "green"))
        print(colored(f"[+] SUCCESS! Output saved as:", "cyan", attrs=['bold']))
        print(colored(f"[+] {output_apk}", "cyan", attrs=['bold']))
        
    except KeyboardInterrupt:
        print(colored("\n[-] Process interrupted", "red"))
        cleanup_files()
        sys.exit(1)
    except Exception as e:
        print(colored(f"\n[-] Error: {str(e)}", "red"))
        cleanup_files()
        sys.exit(1)

if __name__ == "__main__":
    main()
