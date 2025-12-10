import requests
import re
import sys
import json
import pandas as pd
import os

# --- Configuration ---

# 1. AUTOLOGIN URL
login_url = "https://pars.procurement.sa.gov.au/AutoLogin.aspx"
login_params = {
    "Username": "guest_user",
    "Password": "fL656jgeLHtM",
    "redir": "EFormRecord.aspx?EFormType=Forward%20Procurement%20Plan"
}
login_headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}

# 2. GET CSRF TOKEN URL
get_csrf_url = "https://pars.procurement.sa.gov.au/records/Forward%20Procurement%20Plan/new?EFormType=Forward%20Procurement%20Plan"

# 3. POST HEADERS (URL will be built dynamically)
post_headers = {
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://pars.procurement.sa.gov.au",
    "Referer": get_csrf_url,
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}

# --- FUNCTION: JSON TO CSV ---
def convert_json_to_csv(json_file_path, csv_file_path):
    try:
        print(f"\n--- 5. Converting {json_file_path} to CSV ---")
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if rows exist
        if not data.get('result', {}).get('data', {}).get('rows'):
            print("Warning: JSON contains no rows. CSV will be empty.")
            return

        headers = [col['heading'] for col in data['result']['columns']]
        data_rows = data['result']['data']['rows']
        
        processed_rows = []
        for row in data_rows:
            row_values = []
            for cell in row['values']:
                value = cell.get('display', cell.get('value'))
                row_values.append(value)
            processed_rows.append(row_values)

        df = pd.DataFrame(processed_rows, columns=headers)
        df.to_csv(csv_file_path, index=False, encoding='utf-8-sig')
        print(f"Successfully saved data to {csv_file_path}")

    except Exception as e:
        print(f"Error during CSV conversion: {e}")

# --- MAIN EXECUTION ---

JSON_OUTPUT_FILE = "vendor_panel.json"
CSV_OUTPUT_FILE = "vendor_panel.csv"

with requests.Session() as s:
    try:
        # === PART 1: AUTOLOGIN ===
        print("--- 1. Performing guest autologin ---")
        response_login = s.get(login_url, params=login_params, headers=login_headers, allow_redirects=True)
        response_login.raise_for_status()
        
        if "nimblex_auth_pars" not in s.cookies:
            print("ERROR: Login failed. 'nimblex_auth_pars' cookie not found.")
            sys.exit(1)
        print("Login successful.")

        # === PART 2: EXTRACT CSRF AND SESSION ID ===
        print("\n--- 2. Extracting CSRF & Session ID ---")
        html_content = response_login.text
        
        # A. Extract CSRF
        csrf_pattern = r'csrf:\s*"([^"]+)"'
        csrf_match = re.search(csrf_pattern, html_content)
        if not csrf_match:
            print("ERROR: Could not find CSRF token.")
            sys.exit(1)
        csrf_token = csrf_match.group(1)
        print(f"Found CSRF Token: {csrf_token[:10]}...")

        # B. Extract Session ID (Updated with Multiple Patterns)
        session_id = None
        
        # List of regex patterns to try (UUID is 36 chars: 8-4-4-4-12)
        # 1. Look for API URL inside JS
        # 2. Look for "sessionId": "..." (JSON style)
        # 3. Look for sessionId: "..." (JS object style)
        # 4. Look for generic variable assignment
        patterns = [
            r'site-api/records/session/([a-f0-9\-]{36})',
            r'"sessionId"\s*:\s*"([a-f0-9\-]{36})"',
            r'sessionId\s*:\s*"([a-f0-9\-]{36})"',
            r'session/([a-f0-9\-]{36})',
            r'recordId\s*=\s*["\']([a-f0-9\-]{36})["\']'
        ]

        print("Scanning HTML for Session ID using multiple patterns...")
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                session_id = match.group(1)
                print(f"  Matched Pattern: {pattern}")
                break
        
        if not session_id:
            print("ERROR: Could not find Session ID in HTML using any known pattern.")
            print("Saving HTML for manual inspection...")
            with open("debug_login_page.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            print("Please open 'debug_login_page.html' and search for a UUID (e.g., xxxxxxxx-xxxx-xxxx...).")
            sys.exit(1)

        print(f"Found Session ID: {session_id}")

        # === PART 3: MAKE POST REQUESTS (LOOPING) ===
        print("\n--- 3. Fetching Data (Looping) ---")
        
        # Construct the Dynamic URL
        post_url = f"https://pars.procurement.sa.gov.au/site-api/records/session/{session_id}/command"
        post_headers["X-XSRF-TOKEN"] = csrf_token
        
        all_rows = []
        start_index = 0
        batch_size = 500
        
        while True:
            print(f"Requesting rows starting at {start_index}...")
            
            # Payload construction
            args_payload = {
                "filters": [None, None, None, None, None, None, "", None, None, None, None, None, None],
                "start": start_index,
                "count": batch_size,
                "sort": [] 
            }
            
            payload = {
                "entityType": "control",
                "id": "Control1",
                "name": "TabularReportControl.GetData",
                "arguments": json.dumps(args_payload),
                "readonly": "false"
            }

            response_post = s.post(post_url, headers=post_headers, data=payload)
            response_post.raise_for_status()
            
            data_json = response_post.json()
            rows = data_json.get('result', {}).get('data', {}).get('rows', [])
            
            if not rows:
                print("No rows returned. Loop finished.")
                break
                
            all_rows.extend(rows)
            print(f"  Got {len(rows)} rows. Total: {len(all_rows)}")
            
            if len(rows) < batch_size:
                print("  Batch smaller than limit. End of data reached.")
                break
                
            start_index += batch_size

        # === PART 4: SAVE JSON ===
        if 'result' in data_json:
            # Reconstruct the structure for the converter using the last received JSON structure
            # but replacing the rows with our accumulated list
            data_json['result']['data']['rows'] = all_rows
            
            with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(data_json, f, indent=4)
            print(f"\n--- 4. Saved {len(all_rows)} records to {JSON_OUTPUT_FILE} ---")
            
            # === PART 5: CONVERT ===
            convert_json_to_csv(JSON_OUTPUT_FILE, CSV_OUTPUT_FILE)
        else:
            print("Error: Final JSON structure missing 'result' key.")

    except requests.exceptions.HTTPError as e:
        print(f"\n--- HTTP Error ---")
        print(f"Status: {e.response.status_code}")
        print(f"Response: {e.response.text}") 
    except Exception as e:
        print(f"\n--- Error ---")
        print(e)
