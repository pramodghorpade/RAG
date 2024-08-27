import nest_asyncio
import random

nest_asyncio.apply()
from dotenv import load_dotenv

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from llama_index.core.prompts import PromptTemplate

from llama_index.core.evaluation import (
    DatasetGenerator,
    FaithfulnessEvaluator,
    RelevancyEvaluator
)
from llama_index.llms.openai import OpenAI

import openai
import time
import os

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Read Docs
data_dir = "../data"
documents = SimpleDirectoryReader(data_dir).load_data()

# Create evaluation questions and pick k out of them
num_eval_questions = 25

eval_documents = documents[0:20]
data_generator = DatasetGenerator.from_documents(eval_documents)
eval_questions = data_generator.generate_questions_from_nodes()
k_eval_questions = random.sample(eval_questions, num_eval_questions)

# Define metrics evaluators and modify llama_index faithfullness evaluator prompt to rely on the context
# We will use GPT-4 for evaluating the responses
gpt4 = OpenAI(temperature=0, model="gpt-4o")

# Define service context for GPT-4 for evaluation
service_context_gpt4 = ServiceContext.from_defaults(llm=gpt4)

# Define Faithfulness and Relevancy Evaluators which are based on GPT-4
faithfulness_gpt4 = FaithfulnessEvaluator(service_context=service_context_gpt4)

faithfulness_new_prompt_template = PromptTemplate(""" Please tell if a given piece of information is directly supported by the context.
    You need to answer with either YES or NO.
    Answer YES if any part of the context explicitly supports the information, even if most of the context is unrelated. If the context does not explicitly support the information, answer NO. Some examples are provided below.

    Information: Apple pie is generally double-crusted.
    Context: An apple pie is a fruit pie in which the principal filling ingredient is apples.
    Apple pie is often served with whipped cream, ice cream ('apple pie à la mode'), custard, or cheddar cheese.
    It is generally double-crusted, with pastry both above and below the filling; the upper crust may be solid or latticed (woven of crosswise strips).
    Answer: YES

    Information: Apple pies taste bad.
    Context: An apple pie is a fruit pie in which the principal filling ingredient is apples.
    Apple pie is often served with whipped cream, ice cream ('apple pie à la mode'), custard, or cheddar cheese.
    It is generally double-crusted, with pastry both above and below the filling; the upper crust may be solid or latticed (woven of crosswise strips).
    Answer: NO

    Information: Paris is the capital of France.
    Context: This document describes a day trip in Paris. You will visit famous landmarks like the Eiffel Tower, the Louvre Museum, and Notre-Dame Cathedral.
    Answer: NO

    Information: {query_str}
    Context: {context_str}
    Answer:

    """)

faithfulness_gpt4.update_prompts(
    {"your_prompt_key": faithfulness_new_prompt_template})  # Update the prompts dictionary with the new prompt template
relevancy_gpt4 = RelevancyEvaluator(service_context=service_context_gpt4)


# Function to evaluate metrics for each chunk size
# Define function to calculate average response time, average faithfulness and average relevancy metrics for given chunk size
# We use GPT-3.5-Turbo to generate response and GPT-4 to evaluate it.
def evaluate_response_time_and_accuracy(chunk_size, eval_questions):
    """
    Evaluate the average response time, faithfulness, and relevancy of responses generated by GPT-3.5-turbo for a given chunk size.
    
    Parameters:
    chunk_size (int): The size of data chunks being processed.
    
    Returns:
    tuple: A tuple containing the average response time, faithfulness, and relevancy metrics.
    """

    total_response_time = 0
    total_faithfulness = 0
    total_relevancy = 0

    # create vector index
    llm = OpenAI(model="gpt-3.5-turbo")

    service_context = ServiceContext.from_defaults(llm=llm, chunk_size=chunk_size, chunk_overlap=chunk_size // 5)
    vector_index = VectorStoreIndex.from_documents(
        eval_documents, service_context=service_context
    )
    # build query engine
    query_engine = vector_index.as_query_engine(similarity_top_k=5)
    num_questions = len(eval_questions)

    # Iterate over each question in eval_questions to compute metrics.
    # While BatchEvalRunner can be used for faster evaluations (see: https://docs.llamaindex.ai/en/latest/examples/evaluation/batch_eval.html),
    # we're using a loop here to specifically measure response time for different chunk sizes.
    for question in eval_questions:
        start_time = time.time()
        response_vector = query_engine.query(question)
        elapsed_time = time.time() - start_time

        faithfulness_result = faithfulness_gpt4.evaluate_response(
            response=response_vector
        ).passing

        relevancy_result = relevancy_gpt4.evaluate_response(
            query=question, response=response_vector
        ).passing

        total_response_time += elapsed_time
        total_faithfulness += faithfulness_result
        total_relevancy += relevancy_result

    average_response_time = total_response_time / num_questions
    average_faithfulness = total_faithfulness / num_questions
    average_relevancy = total_relevancy / num_questions

    return average_response_time, average_faithfulness, average_relevancy


# Test different chunk sizes 
chunk_sizes = [128, 256]

for chunk_size in chunk_sizes:
    avg_response_time, avg_faithfulness, avg_relevancy = evaluate_response_time_and_accuracy(chunk_size,
                                                                                             k_eval_questions)
    print(
        f"Chunk size {chunk_size} - Average Response time: {avg_response_time:.2f}s, Average Faithfulness: {avg_faithfulness:.2f}, Average Relevancy: {avg_relevancy:.2f}")