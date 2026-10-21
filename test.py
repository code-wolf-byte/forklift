from asu_discord.cogs.forklift_qna import ForkmanQNA
from dotenv import load_dotenv
import os
import base64
import requests
inp = ''
load_dotenv()
token = os.getenv('CREATEAI_API_KEY').strip()
url = "https://api-main-beta.aiml.asu.edu/query"
qna = ForkmanQNA(token, url=url)

while True:
    inp = input("Question (blank to quit): ").strip()
    if not inp:
        break
    result = qna.get_answer("", inp)
    print(result["full_message"])
    print(result["raw_response"])