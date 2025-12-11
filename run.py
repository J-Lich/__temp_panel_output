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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-AU,en;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Referer": "https://www.buying4.sa.gov.au/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
}

# 2. GET CSRF TOKEN URL
get_csrf_url = "https://pars.procurement.sa.gov.au/records/Forward%20Procurement%20Plan/new?EFormType=Forward%20Procurement%20Plan"

# 3. POST DATA URL (session ID will be inserted dynamically)
post_url_template = "https://pars.procurement.sa.gov.au/site-api/records/session/{session_id}/command"

post_headers = {
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://pars.procurement.sa.gov.au",
    "Referer": get_csrf_url,
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
}
post_data = {
    "entityType": "control",
    "id": "Control1",
    "name": "TabularReportControl.GetData",
    "arguments": '{"filters":[null,null,null,null,null,null,"",null,null,null,null,null,null],"start":0,"count":500,"sort":[]}',
    "readonly": "false"
}


# --- Function to convert JSON to CSV ---
def convert_json_to_csv(json_file_path, csv_file_path):
    """
    Reads the specific JSON file structure and converts it to a CSV.
    """
    try:
        print(f"\n--- 5. Converting {json_file_path} to CSV ---")
        
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 1. Extract column headers from the 'columns' list
        headers = [col['heading'] for col in data['result']['columns']]
        
        # 2. Get the list of row data
        data_rows = data['result']['data']['rows']
        
        processed_rows = []
        # 3. Loop through each row
        for row in data_rows:
            row_values = []
            # 4. Loop through each cell in the 'values' list
            for cell in row['values']:
                # Get the 'display' value. If it's not present, get 'value'.
                value = cell.get('display', cell.get('value'))
                row_values.append(value)
            
            processed_rows.append(row_values)

        # 5. Create the DataFrame with the extracted headers
        df = pd.DataFrame(processed_rows, columns=headers)
        
        # 6. Save to CSV
        df.to_csv(csv_file_path, index=False, encoding='utf-8-sig')
        print(f"Successfully saved data to {csv_file_path}")

    except KeyError as e:
        print(f"Error during CSV conversion: JSON structure was not as expected. Missing key: {e}")
    except Exception as e:
        print(f"Error during CSV conversion: {e}")
        print("The JSON file was saved, but CSV conversion failed.")


# --- Main Script Execution ---

# Define output filenames
JSON_OUTPUT_FILE = "vendor_panel.json"
CSV_OUTPUT_FILE = "vendor_panel.csv"

# Use a session to automatically persist cookies through all 3 steps
with requests.Session() as s:
    try:
        # === PART 1: AUTOLOGIN ===
        print("--- 1. Performing guest autologin ---")
        response_login = s.get(
            login_url, 
            params=login_params, 
            headers=login_headers, 
            allow_redirects=True
        )
        response_login.raise_for_status()
        
        if "nimblex_auth_pars" not in s.cookies:
            print("ERROR: Login failed. 'nimblex_auth_pars' cookie not found.")
            sys.exit(1)
        print("Login successful. Auth cookie 'nimblex_auth_pars' was set.")

        # === PART 2: EXTRACT CSRF TOKEN ===
        print("\n--- 2. Extracting CSRF token from login redirect page ---")
        html_content = response_login.text
        
        # Extract CSRF token
        csrf_pattern = r'csrf:\s*"([^"]+)"'
        csrf_match = re.search(csrf_pattern, html_content)
        
        if not csrf_match:
            print("\nERROR: Could not find CSRF token in HTML response. Aborting.")
            sys.exit(1)
        csrf_token = csrf_match.group(1)
        print(f"Successfully extracted CSRF Token.")
        
        # === PART 2.5: CREATE A NEW SESSION VIA API ===
        print("\n--- 2.5. Creating new session via API ---")
        
        # Correct endpoint is /sessions/new (plural)
        session_create_url = "https://pars.procurement.sa.gov.au/site-api/records/sessions/new"
        session_headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-XSRF-TOKEN": csrf_token,
            "Origin": "https://pars.procurement.sa.gov.au",
            "Referer": get_csrf_url,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        }
        
        # Data must be form-encoded, not JSON
        session_data = {
            "eForm": "Forward Procurement Plan",
            "parameters": "{}",
            "isMobileVariant": "false",
            "mobileOverride": "false"
        }
        
        try:
            session_response = s.post(session_create_url, headers=session_headers, data=session_data)
            session_response.raise_for_status()
            
            # Save the session response for debugging
            with open('debug_session_response.json', 'w', encoding='utf-8') as f:
                json.dump(session_response.json(), f, indent=4)
            print("Saved session response to debug_session_response.json")
            
            # Extract session ID from the 'sid' field
            session_json = session_response.json()
            session_id = session_json.get('sid')
            
            if not session_id:
                print("\nERROR: Could not extract session ID (sid) from API response.")
                print("Response data:", json.dumps(session_json, indent=2))
                sys.exit(1)
            
            print(f"Successfully created and extracted Session ID: {session_id}")
            
        except requests.exceptions.HTTPError as e:
            print(f"\nERROR: Failed to create session via API")
            print(f"Status Code: {e.response.status_code}")
            print(f"Response: {e.response.text}")
            sys.exit(1)

        # === PART 3: MAKE POST REQUEST ===
        print("\n--- 3. Making POST request (with auth cookies + CSRF) ---")
        
        # Construct the POST URL with the dynamic session ID
        post_url = post_url_template.format(session_id=session_id)
        print(f"POST URL: {post_url}")
        
        post_headers["X-XSRF-TOKEN"] = csrf_token
        response_post = s.post(post_url, headers=post_headers, data=post_data)
        response_post.raise_for_status()
        print(f"POST Status: {response_post.status_code} (Success)")

        # === PART 4: SAVE JSON RESULTS ===
        with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(response_post.json(), f, indent=4)
        print(f"\n--- 4. Successfully saved JSON response to {JSON_OUTPUT_FILE} ---")
        
        # === PART 5: CONVERT TO CSV ===
        convert_json_to_csv(JSON_OUTPUT_FILE, CSV_OUTPUT_FILE)

    except requests.exceptions.HTTPError as e:
        print(f"\n--- HTTP Error ---")
        print(f"Status Code: {e.response.status_code} {e.response.reason}")
    except requests.exceptions.RequestException as e:
        print(f"\n--- A network error occurred ---")
        print(e)
    except Exception as e:
        print(f"\n--- An unexpected error occurred ---")
        print(e)
