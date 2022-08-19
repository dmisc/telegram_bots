#! /usr/bin/python3

import requests

def request_subms(username, item_count = 5):
    url = "https://leetcode.com/graphql/"
    request_data = {
        "query": 
            """query recentAcSubmissions($username: String!, $limit: Int!) {
                recentAcSubmissionList(username: $username, limit: $limit) {
                    id
                    title
                    titleSlug
                    timestamp
                }
            }""",
        "variables": {
            "username": username,
            "limit": item_count,
        },
    }

    headers = {
            "Referer": f"https://leetcode.com/{username}/",
            "Content-Type": "application/json",
    }
                
    x = requests.post(url, json = request_data, headers = headers)

    return x.json()["data"]["recentAcSubmissionList"]


#print(request_subms(username=""))
#print(request_subms(username=""))
#print(x)
#print(x.text)
#print(x.headers)

def request_question_data(title_slug):
    url = "https://leetcode.com/graphql/"
    request_data = {
        "query": 

    #similarQuestions
    #topicTags {
    #  name
    #  slug
    #}
"""
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    title
    titleSlug
    difficulty
    categoryTitle
    stats
  }
}
""",


        "variables": {
	    "titleSlug": title_slug,
        },
    }

    headers = {
            #"Referer": f"https://leetcode.com/{username}/",
            "Content-Type": "application/json",
    }
                
    x = requests.post(url, json = request_data, headers = headers)

    return x.json()["data"]["question"]

print(request_question_data("find-pivot-index"))
print(None)
