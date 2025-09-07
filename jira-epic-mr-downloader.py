#!/usr/bin/env python3

import git
import os,json,argparse
import jira
from jira import JIRA
import requests
from bs4 import BeautifulSoup as bs
from lxml import etree
import re
from termcolor import colored
import urllib.parse
import gitlab
import urllib.request
import threading,time
from urllib.parse import urlparse


OUTPUT_FOLDER = "jira-007-output"
FUNC_COMPLETED = False

def print_progress(string):
    global FUNC_COMPLETED
    animation = [".    ", "..   ", "...  ",".... ","....."," ....","  ...","   ..","    ."]
    i = 0
    while not FUNC_COMPLETED:
        frame = animation[i % len(animation)]
        print(colored(f"\r{string}{frame}","red"), end="", flush=True)
        i += 1
        time.sleep(0.2)  # Adjust sleep time to change the animation speed

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-u','--url',dest='epic_url', help="Jira EPIC URL", required=True)
    parser.add_argument('-gt','--gittoken',dest='gitlab_token',help="Gitlab Token (Optional: Fetched from Env: GITLAB_API_TOKEN)")
    parser.add_argument('-jt','--jiratoken',dest='jira_token',help="Jira Token (Optional: Fetched from Env: JIRA_API_TOKEN)")
    parser.add_argument('-gh','--gitlabhost',dest='gitlab_host',help="Gitlab Host URL (If provided,it verifies if GITLAB_TOKEN is valid initially else proceeds directly)")
    args = parser.parse_args()

    if not args.gitlab_token and not os.getenv("GITLAB_API_TOKEN"):
        exit(colored("[-] Error: Could not fetch Env Variable GITLAB_API_TOKEN. Please set it or provide argument -gt <token>","red"))

    if not args.jira_token and not os.getenv("JIRA_API_TOKEN"):
        exit(colored("[-] Error: Could not fetch Env Variable JIRA_API_TOKEN. Please set it or provide argument -jt <token>","red"))


    return args

# Jira authentication details
def Get_Jira_Object(jira_url):
    global JIRA_API_TOKEN
    headers = JIRA.DEFAULT_OPTIONS["headers"].copy()
    headers["Authorization"] = f"Bearer {JIRA_API_TOKEN}"
    jira=JIRA(server=jira_url, options={"headers": headers})
    return jira


def Get_All_Issues_From_Epic(jira,jira_epic_link):
    global FUNC_COMPLETED
    print_progress_thread = threading.Thread(target=print_progress, args=("[*] Fetching All Jira Issues",))
    print_progress_thread.start()

    epic_name = jira_epic_link.split('/')[-1]
    jql_query = f'"Epic Link" = {epic_name}'

    #Get all issues in the epic
    issues = jira.search_issues(jql_query, maxResults=100)
    FUNC_COMPLETED = True                                    #This will make the while loop false in the print_progress

    print(issues)
    for issue in issues:
        # print(f"{issue.key}: {issue.fields.summary}")      #Print Issue Summary
        # print(f"{issue.key}: {issue.permalink()}")          #Print Issue URL
        Get_Git_Commit_Link_From_Issue(issue.key, epic_name)


def Get_Git_Commit_Link_From_Issue(issueKey, epic_name):
    global JIRA_API_TOKEN
    global JIRA_BASE_URL

    api_url = f"{JIRA_BASE_URL}/rest/api/latest/issue/{issueKey}"
    headers =  {"Authorization" : f"Bearer {JIRA_API_TOKEN}"}

    response = requests.get(api_url,headers=headers)
    json_data = json.loads(response.text)


    try:
        for item in json_data["fields"]["comment"]["comments"]:
            mergeReqBody = item["body"]
            try:
                if "merge_requests" in mergeReqBody:
                    pattern = r"a merge request\|([^]]+)"
                    result = re.search(pattern, mergeReqBody)
                    mr_url = result.group(1)
                    print(colored(f"\n[-] {mr_url}","magenta"))
                    Download_Code_From_MR(mr_url,epic_name)
            except Exception as e:
                print(colored(f"ERROR: {e}","red"))
    except Exception as e:
        print(colored(f"ERROR: {e}","red"))


def Download_Code_From_MR(mr_url,epic_name):
    global GITLAB_API_TOKEN    

    parsed_url = urlparse(mr_url)
    GITLAB_BASE_URL = f"{parsed_url.scheme}://{parsed_url.netloc}"   #Uncomment this and delete below line later
    GITLAB_API = f"{GITLAB_BASE_URL}/api/v4/"

    # url = "https://gitlab.sickuritywizard.com/baseproject/projectName/-/merge_requests/177"
    url_parts = mr_url.split("/")
    project_id = url_parts[3] + "%2F" + url_parts[4]
    merge_request_id = url_parts[7]

    # Build API URL for merge request changes
    api_url = f"{GITLAB_API}projects/{project_id}/merge_requests/{merge_request_id}/changes"

    # Add GitLab API access token to request headers
    headers = {"PRIVATE-TOKEN": GITLAB_API_TOKEN}

    # Send GET request to GitLab API
    response = requests.get(api_url, headers=headers)

    # Parse and return changes from response
    response_json = response.json()

    changes = response_json["changes"]
    for change in changes:
        filepath = change['new_path']
        diff = change['diff']
        create_diff_file(filepath,diff,epic_name)

    # return response_json["changes"]

def create_diff_file(filepath,diff,epic_name):
    filepath    = os.path.join(OUTPUT_FOLDER,epic_name,filepath)    #To create file   (Ex: jira-007-output/EPIC_ID/api/xxx/myfile.text)
    folder_path = "/".join(filepath.split("/")[:-1])                #To create folder (Ex: jira-007-output/EPIC_ID/api/xxx)

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    with open(filepath,"w") as diff_file:
        diff_file.write(diff)

    beautify_file(filepath)


def beautify_file(filepath):
    with open(filepath,"r") as diff_file:
        processed_file_content = ""
        for line in diff_file:
            if line.startswith("+"):
                processed_file_content += line[1:]
            elif line.startswith("-"):
                continue
            else:
                line = re.sub(r'@@ -\d+,\d+ \+\d+,\d+ @@ ', '', line)
                processed_file_content += line

    with open(filepath,"w") as diff_file:
        diff_file.write(processed_file_content)

    print(colored(f"  --> {filepath}","white"))


def prechecks(GITLAB_BASE_URL, JIRA_BASE_URL,GITLAB_API_TOKEN,JIRA_API_TOKEN):
    #GIT TOKEN VERIFY
    if GITLAB_BASE_URL:
        gitVerifyURL = f"{GITLAB_BASE_URL}/api/v4/personal_access_tokens/self"
        headers = {"PRIVATE-TOKEN" : GITLAB_API_TOKEN}
        res = requests.get(gitVerifyURL,headers=headers)
        if res.status_code != 200:
            exit(colored(f"[X] Gitlab Token is invalid: {res.status_code}","red"))
        print(colored("[-] Gitlab Token successfully validated","magenta"))
    else:
        print(colored("[-] Gitlab Token verification Skipped as Gitlab Host (-gh) not provided","red"))

    #JIRA TOKEN VERIFY
    git_verify_url = f"{JIRA_BASE_URL}/rest/api/3/myself"
    headers = {"Authorization" : f"Bearer {JIRA_API_TOKEN}", "Accept": "application/json"}
    res = requests.get(git_verify_url,headers=headers)
    if "X-AUSERNAME" in res.headers and res.headers["X-AUSERNAME"] == "anonymous":
        exit(colored(f"[X] Jira Token is invalid: {res.headers['X-AUSERNAME']}","red"))
    print(colored(f"[-] Jira Token successfully validated: {res.headers['X-AUSERNAME']}","magenta"))

def main():
    global GITLAB_API_TOKEN
    global JIRA_API_TOKEN
    global JIRA_BASE_URL

    args = get_args()
    JIRA_EPIC_URL = args.epic_url
    GITLAB_API_TOKEN = args.gitlab_token or os.getenv("GITLAB_API_TOKEN")
    JIRA_API_TOKEN =  args.jira_token or os.getenv("JIRA_API_TOKEN")

    #Jira Base URL
    parsed_url = urlparse(JIRA_EPIC_URL)
    JIRA_BASE_URL = f"{parsed_url.scheme}://{parsed_url.netloc}"

    #Gitlab Base URL
    GITLAB_BASE_URL = None
    if args.gitlab_host:
        GITLAB_BASE_URL = args.gitlab_host

    print("[-] " + colored("GET MERGE REQUESTS FROM JIRA EPIC",attrs=['bold','underline']) + " [-]",end="\n\n")
    prechecks(GITLAB_BASE_URL, JIRA_BASE_URL, GITLAB_API_TOKEN, JIRA_API_TOKEN)
    jira_obj = Get_Jira_Object(JIRA_BASE_URL)
    Get_All_Issues_From_Epic(jira_obj, JIRA_EPIC_URL)
    print("\n[+] " + colored("COMPLETED",attrs=['bold','underline']) + " [+]")

if __name__ == '__main__':
    main()
