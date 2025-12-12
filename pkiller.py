import os
import sys
import shutil
import subprocess
import re
import threading
import time
import argparse
import glob
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

def remove_pairip_smali(decoded_dir):
    print(colored("\n[2/5] Removing PairIP files...", "white"))
    pairip_path = os.path.join(decoded_dir, "smali/classes/com/pairip")
    if os.path.exists(pairip_path):
        shutil.rmtree(pairip_path)
        print(colored("  [+] Removed PairIP smali directory", "green"))
    else:
        found = False
        smali_dir = os.path.join(decoded_dir, "smali/classes")
        if os.path.exists(smali_dir):
            for root, dirs, files in os.walk(smali_dir):
                for dir_name in dirs:
                    if 'pairip' in dir_name.lower() or 'license' in dir_name.lower():
                        dir_path = os.path.join(root, dir_name)
                        shutil.rmtree(dir_path)
                        found = True
                        print(colored(f"  [+] Removed: {dir_name}", "green"))
        if not found:
            print(colored("  [*] No PairIP directories found", "white"))
    return True

def clean_manifest(decoded_dir):
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

def sign_apk(apk_path):
    print(colored("\n[5/5] Signing APK...", "white"))
    
    keystore_path = os.path.join(os.environ.get('PREFIX', '/data/data/com.termux/files/usr'), 
                                'share', 'PKiller', 'key', 'PKiller.keystore')
    
    if not os.path.exists(keystore_path):
        if not create_keystore(keystore_path):
            print(colored("[-] Cannot proceed without keystore", "red"))
            return None
    
    signed_apk = apk_path.replace('.apk', '_signed.apk')
    
    cmd = [
        'apksigner', 'sign',
        '--ks', keystore_path,
        '--ks-pass', 'pass:pkiller',
        '--ks-key-alias', 'PKiller',
        '--key-pass', 'pass:pkiller',
        '--out', signed_apk,
        apk_path
    ]
    
    if run_with_spinner(cmd, "APK signed", "Sign failed"):
        return signed_apk
    return None

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
    
    temp_apk = os.path.join(os.getcwd(), "temp_rebuilt.apk")
    if os.path.exists(temp_apk) and (not output_apk or temp_apk != output_apk):
        os.remove(temp_apk)

def main():
    show_banner()
    
    parser = argparse.ArgumentParser(description='Remove PairIP license from APK', 
                                   add_help=False)
    parser.add_argument('apk_path', help='Path to the APK file', nargs='?')
    parser.add_argument('-o', '--output', help='Output APK filename')
    parser.add_argument('-h', '--help', action='store_true', help='Show help')
    
    args = parser.parse_args()
    
    if args.help or not args.apk_path:
        print(colored("Usage:", "white"))
        print(colored(f"  {script_name} <apk_file> [-o output.apk]", "green"))
        print(colored("\nExamples:", "white"))
        print(colored(f"  {script_name} myapp.apk", "green"))
        print(colored(f"  {script_name} myapp.apk -o patched_app.apk", "green"))
        print(colored(f"  {script_name} myapp.apk --output custom_name.apk", "green"))
        print(colored("\nDefault output: <original_name>_pairip_killed.apk", "cyan"))
        sys.exit(0)
    
    input_apk = args.apk_path
    
    if not os.path.exists(input_apk):
        print(colored(f"\n[-] File not found: {input_apk}", "red"))
        sys.exit(1)
    
    if not check_tools():
        sys.exit(1)
    
    # Determine output filename
    if args.output:
        output_apk = args.output
        # Ensure .apk extension
        if not output_apk.lower().endswith('.apk'):
            output_apk += '.apk'
        output_apk = os.path.join(os.getcwd(), output_apk)
    else:
        base_name = os.path.splitext(os.path.basename(input_apk))[0]
        output_apk = os.path.join(os.getcwd(), f"{base_name}_pairip_killed.apk")
    
    decoded_dir = "decoded_temp"
    
    try:
        if not decode_apk(input_apk, decoded_dir):
            sys.exit(1)
        
        remove_pairip_smali(decoded_dir)
        clean_manifest(decoded_dir)
        
        temp_apk = os.path.join(os.getcwd(), "temp_rebuilt.apk")
        if not rebuild_apk(decoded_dir, temp_apk):
            sys.exit(1)
        
        signed_apk = sign_apk(temp_apk)
        
        if not signed_apk:
            print(colored("[-] Failed to sign APK", "red"))
            cleanup_files()
            sys.exit(1)
        
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
