#!/usr/bin/env python3

import os
from heapq import merge

import requests
from urllib.parse import urlparse, quote
from termcolor import colored
import argparse,re
import pdb

MR_OUTPUT_FOLDER = "MR-Download-Results"
COMMIT_OUTPUT_FOLDER = "Commit-Download-Results"


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-cu','--commit-url',dest='commit_url', help="Commit Request URL")
    parser.add_argument('-cf','--commit-file',dest='commit_file', help="Commit Request File")
    parser.add_argument('-mu','--merge-url',dest='mr_url', help="Merge Request URL")
    parser.add_argument('-mf','--merge-file',dest='mr_file', help="Merge Request File")
    parser.add_argument('-t','--token',dest='gitlab_token',help="Gitlab Token (Optional: Fetched from Env: GITLAB_API_TOKEN)")
    parser.add_argument('-ff','--full-file',action="store_true",dest='full_file',help="Download Complete File (Default: Downloads only diff)",default=False)
    args = parser.parse_args()

    if not args.gitlab_token and not os.getenv("GITLAB_API_TOKEN"):
        exit(colored("[-] Error: Could not fetch Env Variable GITLAB_API_TOKEN. Please set it or provide argument -t <token>","red"))

    if not args.commit_url and not args.commit_file and not args.mr_url and not args.mr_file:
        exit(colored("[-] Error: Either commit_url or commit_file or mr_url or mr_file should be provided","red"))
    

    return args


def Download_Code_From_MR(mr_url):
    global GITLAB_API_TOKEN, DOWNLOAD_COMPLETE_FILE
    parsed_url = urlparse(mr_url)
    gitlab_api = f"{parsed_url.scheme}://{parsed_url.netloc}/api/v4"
                  #https://gitlab.host.com/api/v4"

    # url = "https://gitlab.gg.com/projectname/subproject/-/merge_requests/177"
    url_parts = mr_url.split("/")
    project_id = url_parts[3] + "%2F" + url_parts[4]
    merge_request_id = url_parts[7]

    # Build API URL for merge request changes
    api_url = f"{gitlab_api}/projects/{project_id}/merge_requests/{merge_request_id}/changes"

    headers = {"PRIVATE-TOKEN": GITLAB_API_TOKEN}
    response = requests.get(api_url, headers=headers)
    response_json = response.json()

    source_branch = response_json["source_branch"]

    changes = response_json["changes"]
    for change in changes:
        filepath = change['new_path']

        #TODO: Download Complete File (Not Working)
        # if DOWNLOAD_COMPLETE_FILE:
        #     encoded_filepath = quote(filepath, safe='')       #filepath=/src/something/gg.java
        #     raw_file_url = f'{gitlab_api}/projects/{project_id}/repository/files/{encoded_filepath}/raw?ref={source_branch}'
        #     print(raw_file_url)
        #     codediff = requests.get(raw_file_url,headers=headers).text
        # else:
            # codediff = change["diff"]

        codediff = change["diff"]
        save_diff_to_file(filepath, codediff)


def Download_Code_From_Commit_Url(commit_url):
    global GITLAB_API_TOKEN, DOWNLOAD_COMPLETE_FILE
    parsed_url = urlparse(commit_url)
    gitlab_api = f"{parsed_url.scheme}://{parsed_url.netloc}/api/v4"
                  #https://gitlab.host.com/api/v4"

    # url = "https://gitlab.gg.com/projectname/subproject/-/commit/commithash"
    url_parts = commit_url.split("/")
    project_id = url_parts[3] + "%2F" + url_parts[4]
    commit_hash= url_parts[7].split("?")[0]

    api_url = f"{gitlab_api}/projects/{project_id}/repository/commits/{commit_hash}/diff"
    # print(api_url)

    headers = {"PRIVATE-TOKEN": GITLAB_API_TOKEN}
    response = requests.get(api_url, headers=headers)
    response_json = response.json()

    for item in response_json:
        filepath = item["new_path"]

        if DOWNLOAD_COMPLETE_FILE:
            encoded_filepath = quote(filepath, safe='')       #filepath=/src/something/gg.java
            raw_file_url = f'{gitlab_api}/projects/{project_id}/repository/files/{encoded_filepath}/raw?ref={commit_hash}'
            print(raw_file_url)
            codediff = requests.get(raw_file_url,headers=headers).text

        else:
            codediff = item["diff"]

        save_diff_to_file(filepath, codediff)


def save_diff_to_file(filepath, codediff):
    filename = filepath.split("/")[-1]
    folder = "/".join(filepath.split("/")[:-1])
    if folder != "":
        os.makedirs(folder, exist_ok=True)
    with open (filepath, "w") as fileptr:
        fileptr.write(codediff)

    beautify_file(filepath)


def beautify_file(filepath):
    with open(filepath,"r") as diff_file:
        processed_file_content = ""
        for line in diff_file:
            if line.startswith("+") or line.startswith("-"):
                processed_file_content += line[1:]
            else:
                line = re.sub(r'@@ -\d+,\d+ \+\d+,\d+ @@ ', '', line)
                processed_file_content += line

    with open(filepath,"w") as diff_file:
        diff_file.write(processed_file_content)

    print(colored(f"|--> File: ","yellow"),colored(f"{filepath}","white"))


def verify_gitlab_token(gitlab_url):
    global GITLAB_API_TOKEN

    #Get Base URL
    parsed_url = urlparse(gitlab_url)
    GITLAB_BASE_URL = f"{parsed_url.scheme}://{parsed_url.netloc}"

    git_verify_url = f"{GITLAB_BASE_URL}/api/v4/personal_access_tokens/self"
    headers = {"PRIVATE-TOKEN" : GITLAB_API_TOKEN}
    res = requests.get(git_verify_url,headers=headers)
    if res.status_code != 200:
        exit(colored(f"[X] Gitlab Token is Invalid: {res.status_code}","red"))
    print(colored("[-] Gitlab Token successfully validated","light_magenta"))



def main():
    global GITLAB_API_TOKEN
    global DOWNLOAD_COMPLETE_FILE

    args = get_args()
    GITLAB_API_TOKEN = args.gitlab_token or os.getenv("GITLAB_API_TOKEN")

    curr_dir = os.getcwd()
    os.makedirs("results", exist_ok=True)
    os.chdir("results")

    DOWNLOAD_COMPLETE_FILE = args.full_file

    if args.commit_url:
        verify_gitlab_token(args.commit_url)
        Download_Code_From_Commit_Url(args.commit_url)
        #Example_Commit_URL = "https://gitlab.gg.com/projectname/subproject/-/commit/commithash"

    elif args.mr_url:
        verify_gitlab_token(args.mr_url)
        Download_Code_From_MR(args.mr_url)
        #Example_MR_URL = "https://gitlab.gg.com/projectname/subproject/-/merge_requests/177"

    elif args.commit_file:
        with open(os.path.join(curr_dir, args.commit_file), "r") as fileptr:
            urls = fileptr.readlines()
            verify_gitlab_token(urls[0].strip())
            for commit_url in urls:
                commit_url = commit_url.strip()
                print(colored(f"\n[-] {commit_url}","cyan"))
                Download_Code_From_Commit_Url(commit_url)

    elif args.mr_file:
        with open(os.path.join(curr_dir, args.mr_file), "r") as fileptr:
            urls = fileptr.readlines()
            verify_gitlab_token(urls[0].strip())
            for merge_url in urls:
                merge_url = merge_url.strip()
                print(colored(f"\n[-] {merge_url}","cyan"))
                Download_Code_From_MR(merge_url)

main()


'''
#TODO
1)Add support for full file download even in MergeRequests
2)Test with multiple Commit requests, as last time it was given empty response for few files
'''