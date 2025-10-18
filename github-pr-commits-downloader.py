#!/usr/bin/env python3

import os

import requests
from urllib.parse import urlparse, quote
from termcolor import colored
import argparse,re
import base64
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-pru','--pr-url',dest='pullrequest_url', help="Pull Request URL")
    parser.add_argument('-prf','--pr-file',dest='pr_file', help="PullRequest File")
    parser.add_argument('-cu','--commit-url',dest='commit_url', help="Commit Request URL")
    parser.add_argument('-cf','--commit-file',dest='commit_file', help="Commit Request File")
    parser.add_argument('-t','--token',dest='github_token',help="Github Token (Optional: Fetched from Env: GITHUB_API_TOKEN)")
    parser.add_argument('-do','--diff-only',action="store_true",dest='diff_only',help="Download diff only (Default: Downloads complete file)", default=False)
    parser.add_argument('-mt','--threads',dest='multithread',help="Download using multiple threads (Default: Single Thread)", default=False, type=int)
    args = parser.parse_args()

    if not args.github_token and not os.getenv("GITHUB_API_TOKEN"):
        exit(colored("[-] Error: Could not fetch Env Variable GITHUB_API_TOKEN. Please set it or provide argument -t <token>","red"))

    if not args.commit_url and not args.commit_file and not args.pr_file and not args.pullrequest_url:
        exit(colored("[-] Error: Either commit_url or commit_file or pr_url or pr_file should be provided","red"))
    

    return args

def get_github_api_baseurl(github_url):
    parsed_url = urlparse(github_url)
    github_api_base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/api/v3"  #https://github.host.com/api/v3
    return github_api_base_url


def create_results_dir(results_dir):
    if os.path.exists(results_dir):
        print(colored("[-] Directory already exists: ","red"),colored(f"{results_dir}","light_red"))
        delete_dir = input(colored("[-] Delete existing directory(N/y): ","light_grey"))
        if delete_dir.upper() == "Y":
            shutil.rmtree(results_dir)
        else:
            print(colored("\nExiting... ","magenta"))
            exit()

    os.mkdir(results_dir)


#Example PR URL: https://github.host.com/OWNERNAME/REPONAME/pulls/pullnumber
def download_code_from_pr_url(pr_url):
    #Create Results Folder
    pr_url_dir = pr_url.split("/")
    results_dir = f"{pr_url_dir[4]}_{pr_url_dir[5]}_{pr_url_dir[-1]}"     #owner_repo_pullnumber

    try:
        os.mkdir(results_dir)
    except Exception as e:
        logging.info(colored("[X] Directory Already Exists: ","red"),colored(f"{results_dir}","light_red"))
        exit(1)

    #Get Base URL
    base_url = get_github_api_baseurl(pr_url)
    pr_uri_list = pr_url.split("/")[3:]
    owner,repo,pulls,pull_number = pr_uri_list[0],pr_uri_list[1],"pulls",pr_uri_list[3]  #URL has pull, but api requires pulls

    #Git Default Returns 30 results, so loop to get all pages
    page=0
    completed = False
    count = 0
    while True:
        page +=1
        fetch_pr_api = f"{base_url}/repos/{owner}/{repo}/{pulls}/{pull_number}/files?page={page}"
        headers = {"Authorization": f"token {GITHUB_API_TOKEN}", "Accept": "application/vnd.github.v3.diff"}
        response = requests.get(fetch_pr_api, headers=headers).json()
        res_content_len = len(response)
        if len(response) == 0:
            break

        for item in response:
            count+=1
            file_name = item.get("filename")
            changed_file_sha = item.get("sha")

            fetch_file_api = f"{base_url}/repos/{owner}/{repo}/git/blobs/{changed_file_sha}"
            response = requests.get(fetch_file_api, headers=headers).json()
            file_content_base64 = response.get("content").replace("\n", "")
            try:
                file_content = base64.b64decode(file_content_base64).decode()
                logging.info(colored("[File] ","light_grey") + colored(f"{file_name}","light_blue"))
            except UnicodeDecodeError as e:
                file_content = base64.b64decode(file_content_base64).decode('utf-8', errors='replace')
                logging.info(colored("[Error]","red") + colored(f"Failed Decoding: {file_name} (Saved file without decoding)","light_red"))

            folder = os.path.dirname(file_name)
            if folder:                                    #folder will be empty if file is in root folder
                os.makedirs(os.path.join(results_dir,folder), exist_ok=True)
            with open(os.path.join(results_dir,file_name), "w") as fp:
                fp.write(file_content)


    # print(colored(f"\n[{pr_url}] ","yellow"),colored(f" -> Files Downloaded: {count}","light_cyan"))
    return {
        "pr_url": pr_url,
        "file_count": count,
    }


#Fetches all diff as a single response
def download_only_diff_from_pr_url(pr_url):
    global GITHUB_API_TOKEN

    #Get Base URL
    base_url = get_github_api_baseurl(pr_url)
    pr_uri_list = pr_url.split("/")[3:]
    owner,repo,pulls,pull_number = pr_uri_list[0],pr_uri_list[1],"pulls",pr_uri_list[3]  #URL has pull, but api requires pulls
    final_api_url = f"{base_url}/repos/{owner}/{repo}/{pulls}/{pull_number}"
    headers = {"Authorization": f"token {GITHUB_API_TOKEN}", "Accept": "application/vnd.github.v3.diff"}
    response = requests.get(final_api_url, headers=headers)

    pr_url_dir = pr_url.split("/")
    results_file = f"{pr_url_dir[4]}_{pr_url_dir[5]}_{pr_url_dir[-1]}.txt"     #owner_repo_pullnumber
    with open(results_file, "w") as fp:
        fp.write(response.text)
    print(colored(f"|{pr_url}| -> ","yellow"),colored(f"{results_file}","white"))


#Downloads complete files from commit url
def download_code_from_commit_url(commit_url):

    #Create Results Folder
    results_dir = f"commit_{commit_url.split("/")[-1]}"
    parent_dir = os.getcwd()
    create_results_dir(results_dir)
    os.chdir(results_dir)

    base_url = get_github_api_baseurl(commit_url)
    headers = {"Authorization": f"token {GITHUB_API_TOKEN}", "Accept": "application/vnd.github+json"}

    commit_url_list = commit_url.split("/")[3:]
    owner,repo,commit_sha = commit_url_list[0],commit_url_list[1],commit_url_list[3]


    count=0
    page=0
    while True:
        page +=1
        get_commit_api = f"{base_url}/repos/{owner}/{repo}/commits/{commit_sha}?page={page}"
        headers = {"Authorization": f"token {GITHUB_API_TOKEN}", "Accept": "application/vnd.github+json"}
        response = requests.get(get_commit_api, headers=headers).json()

        all_files = response.get("files",[])
        if len(all_files) == 0:
            break

        for item in response.get("files"):
            count+=1
            file_name = item.get("filename")
            changed_file_sha = item.get("sha")

            fetch_file_api = f"{base_url}/repos/{owner}/{repo}/git/blobs/{changed_file_sha}"
            response = requests.get(fetch_file_api, headers=headers).json()
            file_content_base64 = response.get("content").replace("\n", "")
            try:
                file_content = base64.b64decode(file_content_base64).decode()
                print(colored("[File] ","light_grey"),colored(f"{file_name}","light_blue"))
            except UnicodeDecodeError as e:
                file_content = base64.b64decode(file_content_base64).decode('utf-8', errors='replace')
                print(colored("[Error]","red"),colored(f"Failed Decoding: {file_name} (Saved file without decoding)","light_red"))

            folder = os.path.dirname(file_name)
            if folder:                                    #folder will be empty if file is in root folder
                os.makedirs(folder, exist_ok=True)
            with open(file_name, "w") as fp:
                fp.write(file_content)


    print(colored("\n[Completed] ","yellow"),colored(f"Total Files Downloaded: {count}","light_cyan"))
    os.chdir(parent_dir)




#Downloads Only Diff
def download_only_diff_from_commit_url(commit_url):
    base_url = get_github_api_baseurl(commit_url)
    commit_url_list = commit_url.split("/")[3:]
    owner,repo,commit_sha = commit_url_list[0],commit_url_list[1],commit_url_list[3]  #URL has pull, but api requires pulls
    get_commit_details = f"{base_url}/repos/{owner}/{repo}/commits/{commit_sha}"
    headers = {"Authorization": f"token {GITHUB_API_TOKEN}", "Accept": "application/vnd.github.v3.diff"}
    response = requests.get(get_commit_details, headers=headers)
    print(response.text)



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


def verify_github_token(github_url):
    global GITHUB_API_TOKEN

    github_base_url = get_github_api_baseurl(github_url)
    git_verify_url = f"{github_base_url}/user"
    headers = {"Authorization" : f"token {GITHUB_API_TOKEN}"}
    res = requests.get(git_verify_url,headers=headers)
    if res.status_code != 200:
        exit(colored(f"[X] Github Token is Invalid: {res.status_code}","red"))
    print(colored("[-] Github Token successfully validated","light_magenta"))



def main():
    global GITHUB_API_TOKEN
    global DOWNLOAD_COMPLETE_FILE

    args = get_args()
    GITHUB_API_TOKEN = args.github_token or os.getenv("GITHUB_API_TOKEN")

    curr_dir = os.getcwd()
    os.makedirs("results", exist_ok=True)
    os.chdir("results")

    download_diff_only = args.diff_only

    if args.pullrequest_url:
        verify_github_token(args.pullrequest_url)
        if download_diff_only:
            download_only_diff_from_pr_url(args.pullrequest_url)
        else:
            download_code_from_pr_url(args.pullrequest_url)
        #Example_PullRequest_URL = "https://github.host.com/OWNERNAME/REPONAME/pulls/pullnumber"

    if args.commit_url:
        verify_github_token(args.commit_url)
        if download_diff_only:
            download_only_diff_from_commit_url(args.commit_url)
        else:
            download_code_from_commit_url(args.commit_url)
        #Example_Commit_URL = "https://github.host.com/projectname/subproject/-/commit/commithash"


    elif args.commit_file:
        with open(os.path.join(curr_dir, args.commit_file), "r") as fileptr:
            urls = fileptr.readlines()
            verify_github_token(urls[0].strip())
            for commit_url in urls:
                commit_url = commit_url.strip()
                print(colored(f"\n[-] {commit_url}","cyan"))
                if download_diff_only:
                    download_only_diff_from_commit_url(commit_url)
                else:
                    download_code_from_commit_url(commit_url)


    elif args.pr_file:
        with open(os.path.join(curr_dir, args.pr_file), "r") as fileptr:
            urls = fileptr.readlines()
            verify_github_token(urls[0].strip())

            if args.multithread:                
                logging.info(colored(f"|| Downloading PullRequests [Threads={args.multithread}]","yellow"))

                final_results = []
                with ThreadPoolExecutor(max_workers=args.multithread) as executor:
                    futures = {}
                    for merge_url in urls:
                        merge_url = merge_url.strip()
                        logging.info(colored(f"[-] {merge_url}","cyan"))

                        if download_diff_only:
                            future = executor.submit(download_only_diff_from_pr_url, merge_url) 
                        else:
                            future = executor.submit(download_code_from_pr_url, merge_url) 

                        futures[future] = merge_url

                    #Wait for tasks to complete
                    for future in as_completed(futures):
                        merge_url = futures[future]
                        try:
                            result = future.result()          #Block until thread completes
                            final_results.append(result)
                            logging.info(
                                colored(f"[{result['pr_url']}] ", "green")  + 
                                colored(f" => Files Downloaded: {result['file_count']}", "light_cyan")
                            )
                        except Exception as e:
                            logging.info(colored(f"[Exception] on {merge_url}: {e}","red"))

                #Final Summary
                logging.info(colored("\n[-] SUMMARY [-]", "yellow"))
                for result in final_results:
                    logging.info(
                        colored(f"[{result['pr_url']}] ", "green") +
                        colored(f" => Files Downloaded: {result['file_count']}", "light_cyan")
                    )                    

            else:
                for merge_url in urls:
                    merge_url = merge_url.strip()
                    logging.info(colored(f"\n[-] {merge_url}","cyan"))
                    if download_diff_only:
                        download_only_diff_from_pr_url(merge_url)
                    else:
                        download_code_from_pr_url(merge_url)

                

main()
