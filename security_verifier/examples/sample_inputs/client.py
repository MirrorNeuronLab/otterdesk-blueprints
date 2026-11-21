import requests

def fetch(url):
    return requests.get(url, timeout=4, verify=True)
