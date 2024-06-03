import json
import requests
import datetime
import sqlite3

import asyncio
import logging

from aiogram import Bot,Dispatcher,F
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import TOKEN, WEATHERMAP_API_KEY, OPENAI_API_KEY

from openai import OpenAI


from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI



db = SQLDatabase.from_uri("sqlite:///database.db")

bot = Bot(token=TOKEN)
dp = Dispatcher()


def get_current_weather(city):
    """Get the current weather in a given latitude and longitude"""
    base = "https://api.openweathermap.org/data/2.5/weather"
    key = WEATHERMAP_API_KEY
    request_url = f"{base}?q={city}&appid={key}&units=metric"
    response = requests.get(request_url)

    result = {
        "city": city,
        **response.json()["main"]
    }

    return json.dumps(result)

def get_current_time():
    now = datetime.datetime.now()
    date = now.strftime("%m/%d/%Y")
    time = now.strftime("%H:%M:%S")
    return {"date":date,
            "time":time}

def get_items_from_database(prompt):

    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    agent_executor = create_sql_agent(llm, db=db, agent_type="openai-tools", verbose=True)
    res = agent_executor.invoke(prompt)

    return res["output"]

def create_order(name, date , address):
    with sqlite3.connect("database.db") as connection:
        cursor = connection.cursor()
        res = cursor.execute(f"INSERT INTO orders VALUES('{name}', '{date}', '{address}')")
        print(res)
    return {"result":"Order is created successfully"}






client = OpenAI(
    api_key = OPENAI_API_KEY,
)

def run_conversation(content):
    messages = [{"role": "user", "content": content}]
    tools = [
    {
      "type": "function",
      "function": {
        "name": "get_current_weather",
        "description": "Get the current weather in a given city",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {
              "type": "string",
              "description": "Name of the city or place",
            }
          },
          "required": ["city"],
        },
      },
    },
    {
      "type": "function",
      "function": {
        "name": "get_current_time",
        "description": "Get the current time",
        "parameters": {},
      },
    },
    {
      "type": "function",
      "function": {
        "name": "get_items_from_database",
        "description": "Get items from database based on user prompt",
        "parameters": {
          "type": "object",
          "properties": {
            "prompt": {
              "type": "string",
              "description": "User Prompt",
            }
          },
          "required": ["prompt"],
        },
      },
    },
    {
      "type": "function",
      "function": {
        "name": "create_order",
        "description": "Creates order based on user inputs, like name of lowers, amount, date, time, address",
        "parameters": {
          "type": "object",
          "properties": {
            "name": {
              "type": "string",
              "description": "Names and amout of flowers for order",
            },
            "date": {
              "type": "string",
              "description": "date of order dellivery",
            },
            "address": {
              "type": "string",
              "description": "address of order dellivery",
            }

          },
          "required": ["name","date","address"],
        },
      },
    }
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )   
    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    if tool_calls:
        user_prompt = messages[-1]["content"]
        messages.append(response_message)
        available_functions = {
        "get_current_weather": get_current_weather,
        "get_current_time": get_current_time,
        "get_items_from_database":get_items_from_database,
        "create_order":create_order
        }
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            print(f"Function: {tool_call.function.name}")
            print(f"Params:{tool_call.function.arguments}")
            match function_name:
                case "get_current_weather":
                    function_to_call = available_functions[function_name]
                    function_args = json.loads(tool_call.function.arguments)
                    function_response = function_to_call(
                        city=function_args.get("city")
                    )
                    print(f"API: {function_response}")
                    messages.append(
                        {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                        }
                    )
                case "get_current_time":
                    function_to_call = available_functions[function_name]
                    function_response = function_to_call()
                    print(f"API: {function_response}")
                    messages.append(
                        {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": str(function_response),
                        }
                    )
                
                case "get_items_from_database":
                    function_to_call = available_functions[function_name]
                    function_args = json.loads(tool_call.function.arguments)
                    function_response = function_to_call(user_prompt)
                    print(f"API: {function_response}")
                    messages.append(
                        {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                        }
                    )
                case "create_order":
                    function_to_call = available_functions[function_name]
                    function_args = json.loads(tool_call.function.arguments)
                    function_response = function_to_call(
                        name=function_args.get("name"),
                        date=function_args.get("date"),
                        address=function_args.get("address")
                    )
                    print(f"API: {function_response}")
                    messages.append(
                        {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": str(function_response),
                        }
                    )

        second_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        
        return second_response


@dp.message(CommandStart())
async def cmd_start(message:Message):
    await message.answer('Hello')



@dp.message(F.text)
async def get_message(message:Message):
    #f"You send {message.text}"
    answer = run_conversation(message.text)
    print(answer.choices[0].message.content)
    await message.answer(answer.choices[0].message.content)


async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("exit")
