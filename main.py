import os
import sys
from random import randrange
from typing import List, Union
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile, Path
from fastapi import Form
from typing import List
from fastapi import HTTPException   
from fastapi.logger import logger
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from pyngrok import ngrok
import os
import weaviate
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from supabase import Client, create_client
import shutil
import nest_asyncio
import json
import logging
from llama_index.core.storage.storage_context import StorageContext
from llama_index.core import VectorStoreIndex,SimpleDirectoryReader,ServiceContext,PromptTemplate
from llama_index.vector_stores.weaviate import WeaviateVectorStore
from llama_index.core.response.notebook_utils import display_response
from llama_index.llms.clarifai import Clarifai
from datetime import datetime
from datetime import datetime, timedelta, timezone
from llama_index.core import Document, VectorStoreIndex
# from llama_index.core import StorageContext
import weaviate
from weaviate.classes.init import Auth

nest_asyncio.apply()




# Get the current date and time
current_date_time = datetime.now()
current_date = current_date_time.date()


# Load environment variables from the .env file
load_dotenv()


""" We need to pass the 'Bot User OAuth Token' """
# slack_token = os.environ["SLACK_BOT_TOKEN"]
# slack_token = os.environ.get('SLACK_BOT_TOKEN')
os.environ["CLARIFAI_PAT"] = os.getenv("CLARIFAI_PAT") #you can replace with your PAT or use mine
# slack_token = os.getenv("SLACK__BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_ANON_KEY")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
WEAVIATE_URL = os.getenv("WEAVIATE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY
# slack_client = WebClient(token=slack_token)
supabase: Client = create_client(url, key)

auth_config = weaviate.AuthApiKey(api_key=WEAVIATE_API_KEY)

weaviate_client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_URL,
    auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
    headers={'X-OpenAI-Api-key': OPENAI_API_KEY}
)


# try:
# Posting a message in #random channel
    # response = client.chat_postMessage(channel="project-management", text="Testingaaa \n line 2")
# print("Done 1")
# Sending a message to a particular user
# response = client.chat_postEphemeral(
#     channel="random", text="Hello U06ETJNQX6E", user="U06ETJNQX6E"
# )
# print("Done 2")
# Get basic information of the channel where our Bot has access
# response = client.conversations_info(channel="random")
# print("Done 3")
# Get a list of conversations
# response = client.conversations_list()
# print(response["channels"])

# except SlackApiError as e:
#     assert e.response["error"]
#     print("slack bot error")

app = FastAPI()
import os

def search_and_query(text, ask):
    text_list = [text]
    documents = [Document(text=t) for t in text_list]
    vector_store = WeaviateVectorStore(weaviate_client)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
    query_engine = index.as_query_engine(similarity_top_k=2)
    response = query_engine.query(ask)
    return response

tasks = []

@app.get("/")
def read_root():
    return {"Welcome to Mehvesh's Bot"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}

@app.post("/addtask")
def add_task(text: str = Form(...)):
    tasks.append(text)
    return f"✅ Task Added:  {text}"

@app.post("/tasks", response_class=PlainTextResponse)
def view_tasks():
    if not tasks:
        return "No tasks yet."
    return "📝 Tasks:\n" + "\n".join(f"{i+1}. {task}" for i, task in enumerate(tasks))

@app.post("/deletetask", response_class=PlainTextResponse)
def delete_task(text: str = Form(...)):
    try:
        task_id = int(text.strip()) - 1  # Slack users will use 1-based indexing
        if 0 <= task_id < len(tasks):
            removed = tasks.pop(task_id)
            return f"🗑️ Removed task:\n{removed}"
        else:
            return "❌ Task not found."
    except ValueError:
        return "❌ Please provide a valid task number."
        
@app.post("/transcription")
async def upload_file(file: UploadFile = File(...)):
    contents = await file.read()
    data = contents.decode("utf-8")
    print(type(data))
    try:
        # send to clarifai with prompt to summarize it the transcript
        llm_model = Clarifai(model_url="https://clarifai.com/openai/chat-completion/models/gpt-4-turbo")
        summary = llm_model.complete(prompt=f'''
            Please generate a concise summary of the following Zoom meeting transcription, in this format. Instead of new lines, put the literal 
            characters '\n' without the quotes for formatting:

            Highlighting the key takeaways, major discussion points, and relevant speakers. The summary should follow the format below:

            Topic: [Main topic of the meeting]

            Speakers:
            - [List the speakers' names along with their notable contributions or comments]

            Summary:
            - [Provide a brief summary of the meeting's main topics and discussions, capturing the essence of the conversation]

            Transcription: {data}
            ''')
        summary = (str(summary))
        supabase.table("transcripts").insert({"transcript": data, "summary": summary}).execute()
        slack_client.chat_postMessage(channel="project-management", text=summary)

        return JSONResponse(
            content={"message": "Transcript summarized with gpt-4-turbo and saved to supabase"},
            status_code=200,
        )
    except Exception as e:
        return JSONResponse(
            content={"message": "Error printing file contents"}, status_code=500
        )

@app.post("/dailysummary")
def daily_summary():
    today = date.today()
    today_start = today.isoformat() + "T00:00:00Z"
    today_end = today.isoformat() + "T23:59:59Z"
    #response = supabase.table("transcripts").select('*').execute()
    print("HAHAHAHAHA")
    response = supabase.table("transcripts").select().filter("created_at", "gte", today_start).filter("created_at", "lte", today_end).execute()
    summaries = response.data
    print(summaries)
    summaries_string = "\n\n".join([summary['summary'] for summary in summaries])
    full_message = "*Daily meeting summaries*\n\n" + summaries_string
    print(full_message)
    slack_client.chat_postMessage(channel="project-management", text=full_message)
    return JSONResponse(content="Summaries posted to Slack", status_code=200)
    # response = client.conversations_info(channel="random")
    # response = client.conversations_list()
    # print(response["channels"])



@app.post("/rag")
def daily_summary(data: dict):
    messages = data.get("messages", [])
    user_message = next((msg["content"] for msg in messages if msg["role"] == "user"), None)
    response = supabase.table("transcripts").select('transcript').execute()
    summaries_dated = response.data
    text_string = str(summaries_dated) 
    out = search_and_query(text_string, user_message)
    return JSONResponse(content={"title": f"{out}"}, status_code=200)