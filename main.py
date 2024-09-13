import os
import re
from rich.console import Console
from rich.panel import Panel
from datetime import datetime
import json
from openai import OpenAI
from dotenv import load_dotenv
from tavily import TavilyClient
import logging
import html5lib
from pylint.lint import Run
from pylint.reporters.text import TextReporter
import esprima
import yaml
import css_parser
import xml.etree.ElementTree as ET
import subprocess
from rdflib import Graph, plugins
from rdflib.plugin import register, Parser
from rpy2 import robjects

# Register RDF parsers
register('xml', Parser, 'rdflib.plugins.parsers.rdfxml', 'RDFXMLParser')
register('turtle', Parser, 'rdflib.plugins.parsers.turtle', 'TurtleParser')
register('nt', Parser, 'rdflib.plugins.parsers.ntriples', 'NTriplesParser')

# Load environment variables
load_dotenv()

# Initialize OpenAI API client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Available OpenAI models
ORCHESTRATOR_MODEL = "gpt-4o-mini-2024-07-18"
SUB_AGENT_MODEL = "gpt-4o-mini-2024-07-18"
REFINER_MODEL = "gpt-4o-mini-2024-07-18" 

# Initialize the Rich Console
console = Console()

# Set up logging
logging.basicConfig(level=logging.DEBUG)

def sanitize_filename(filename):
    # Remove any characters that aren't alphanumeric, underscore, hyphen, or period
    sanitized = re.sub(r'[^\w\-.]', '_', filename)
    # Remove leading and trailing underscores
    sanitized = sanitized.strip('_')
    # Replace multiple consecutive underscores with a single one
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized

def validate_code(filename, content):
    # For now, we'll consider all content valid
    return True

def validate_r(content):
    try:
        # Parse the R code
        robjects.r(content)
        return True
    except Exception as e:
        logging.error(f"R code validation error: {str(e)}")
        return False
def validate_html(content):
    try:
        html5lib.parse(content)
        return True
    except Exception as e:
        logging.error(f"HTML validation error: {str(e)}")
        return False

def validate_python(content):
    try:
        pylint_output = StringIO()
        reporter = TextReporter(pylint_output)
        Run(['-'], reporter=reporter, exit=False)
        pylint_stdout = pylint_output.getvalue()
        pylint_stderr = ""
        return True
    except Exception as e:
        logging.error(f"Python validation error: {str(e)}")
        return False

def validate_javascript(content):
    try:
        esprima.parseScript(content)
        return True
    except Exception as e:
        logging.error(f"JavaScript validation error: {str(e)}")
        return False

def validate_css(content):
    try:
        css_parser.parseString(content)
        return True
    except Exception as e:
        logging.error(f"CSS validation error: {str(e)}")
        return False

def validate_json(content):
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError as e:
        logging.error(f"JSON validation error: {str(e)}")
        return False

def validate_xml(content):
    try:
        ET.fromstring(content)
        return True
    except ET.ParseError as e:
        logging.error(f"XML validation error: {str(e)}")
        return False

def validate_yaml(content):
    try:
        yaml.safe_load(content)
        return True
    except yaml.YAMLError as e:
        logging.error(f"YAML validation error: {str(e)}")
        return False

def validate_shell(content):
    try:
        result = subprocess.run(['bash', '-n'], input=content, text=True, capture_output=True)
        if result.returncode != 0:
            logging.error(f"Shell script validation error: {result.stderr}")
            return False
        return True
    except Exception as e:
        logging.error(f"Shell script validation error: {str(e)}")
        return False

def validate_sql(content):
    # This is a basic check. For more robust validation, consider using a SQL parser library.
    if not content.strip().endswith(';'):
        logging.error("SQL validation error: Missing semicolon at the end")
        return False
    return True

def validate_markdown(content):
    # Markdown is very permissive, so we'll just check for some basic structure
    if not re.search(r'^#', content, re.MULTILINE):
        logging.warning("Markdown validation warning: No headers found")
    return True

def validate_rdf(content):
    g = Graph()
    try:
        # Try parsing as RDF/XML
        g.parse(data=content, format='xml')
        return True
    except Exception as e:
        try:
            # Try parsing as Turtle
            g.parse(data=content, format='turtle')
            return True
        except Exception as e:
            try:
                # Try parsing as N-Triples
                g.parse(data=content, format='nt')
                return True
            except Exception as e:
                logging.error(f"RDF validation error: {str(e)}")
                return False

def retry_ai_call(func, max_retries=3, *args, **kwargs):
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            logging.debug(f"AI output (attempt {attempt + 1}):\n{result}")
            if validate_ai_output(result):
                return result
            else:
                logging.error(f"AI output validation failed (attempt {attempt + 1})")
        except Exception as e:
            logging.error(f"AI call failed (attempt {attempt + 1}): {str(e)}")
    raise Exception("Max retries reached for AI call")

def validate_ai_output(output):
    required_patterns = [
        r'Project Name',
        r'<folder_structure>',
        r'Filename:'
    ]
    for pattern in required_patterns:
        if not re.search(pattern, output, re.DOTALL | re.IGNORECASE):
            logging.error(f"Validation failed for pattern: {pattern}")
            logging.debug(f"Output: {output}")
            return False
    logging.info("AI output validation passed")
    return True

def gpt_orchestrator(objective, file_content=None, previous_results=None, use_search=False):
    console.print(f"\n[bold]Calling Orchestrator for your objective[/bold]")
    previous_results_text = "\n".join(previous_results) if previous_results else "None"
    if file_content:
        console.print(Panel(f"File content:\n{file_content}", title="[bold blue]File Content[/bold blue]", title_align="left", border_style="blue"))
    
    messages = [
        {"role": "system", "content": "You are an expert project manager and task orchestrator. Your role is to break down complex objectives into manageable sub-tasks and create detailed prompts for sub-agents to execute these tasks."},
        {"role": "user", "content": f"""Based on the following objective{' and file content' if file_content else ''}, and the previous sub-task results (if any), please:

1. Analyze the current state of the project.
2. Identify the next logical sub-task to be completed.
3. Create a detailed and specific prompt for a sub-agent to execute this task.

When dealing with code tasks:
- Carefully review the code for errors, bugs, or potential improvements.
- Include specific instructions for fixes or enhancements in the sub-task prompt.
- Ensure that the sub-task contributes directly to the overall objective.

If you believe the objective has been fully achieved, begin your response with 'The task is complete:' followed by a summary of the accomplishments.

Objective: {objective}
{'File content:\n' + file_content if file_content else ''}
Previous sub-task results:\n{previous_results_text}

Provide your response in a clear, structured format."""}
    ]

    if use_search:
        messages.append({"role": "user", "content": "Please also generate a JSON object containing a single 'search_query' key, which represents a question that, when asked online, would yield important information for solving the subtask. The question should be specific and targeted to elicit the most relevant and helpful resources. Format your JSON like this, with no additional text before or after:\n{\"search_query\": \"<question>\"}\n"})

    gpt_response = openai_client.chat.completions.create(
        model=ORCHESTRATOR_MODEL,
        messages=messages,
        max_tokens=4096
    )

    response_text = gpt_response.choices[0].message.content
    usage = gpt_response.usage

    console.print(Panel(response_text, title=f"[bold green]gpt Orchestrator[/bold green]", title_align="left", border_style="green", subtitle="Sending task to gpt 👇"))
    console.print(f"Input Tokens: {usage.prompt_tokens}, Output Tokens: {usage.completion_tokens}, Total Tokens: {usage.total_tokens}")

    search_query = None
    if use_search:
        json_match = re.search(r'{.*}', response_text, re.DOTALL)
        if json_match:
            json_string = json_match.group()
            try:
                search_query = json.loads(json_string)["search_query"]
                console.print(Panel(f"Search Query: {search_query}", title="[bold blue]Search Query[/bold blue]", title_align="left", border_style="blue"))
                response_text = response_text.replace(json_string, "").strip()
            except json.JSONDecodeError as e:
                console.print(Panel(f"Error parsing JSON: {e}", title="[bold red]JSON Parsing Error[/bold red]", title_align="left", border_style="red"))
                console.print(Panel(f"Skipping search query extraction.", title="[bold yellow]Search Query Extraction Skipped[/bold yellow]", title_align="left", border_style="yellow"))
        else:
            search_query = None

    return response_text, file_content, search_query

def gpt_sub_agent(prompt, search_query=None, previous_gpt_tasks=None, use_search=False, continuation=False):
    if previous_gpt_tasks is None:
        previous_gpt_tasks = []

    continuation_prompt = "Continuing from the previous answer, please complete the response, maintaining consistency with the original task and format."
    system_message = """You are a specialized AI agent tasked with executing specific sub-tasks within a larger project. Your role is to:

1. Carefully analyze the given prompt and any provided context.
2. Execute the task with high attention to detail and accuracy.
3. When dealing with code:
   - Implement the requested features or fixes.
   - Ensure the code is efficient, well-commented, and follows best practices.
   - Provide explanations for significant changes or design decisions.
4. Format your response clearly, using markdown for structure when appropriate.
5. If the task involves multiple steps, number them for clarity.

Previous tasks and their results:
""" + "\n".join(f"Task: {task['task']}\nResult: {task['result']}" for task in previous_gpt_tasks)
    if continuation:
        prompt = continuation_prompt

    qna_response = None
    if search_query and use_search:
        tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        qna_response = tavily.qna_search(query=search_query)
        console.print(f"QnA response: {qna_response}", style="yellow")

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]

    if qna_response:
        messages.append({"role": "user", "content": f"\nSearch Results:\n{qna_response}"})

    gpt_response = openai_client.chat.completions.create(
        model=SUB_AGENT_MODEL,
        messages=messages,
        max_tokens=4096
    )

    response_text = gpt_response.choices[0].message.content
    usage = gpt_response.usage

    console.print(Panel(response_text, title="[bold blue]gpt Sub-agent Result[/bold blue]", title_align="left", border_style="blue", subtitle="Task completed, sending result to gpt 👇"))
    console.print(f"Input Tokens: {usage.prompt_tokens}, Output Tokens: {usage.completion_tokens}, Total Tokens: {usage.total_tokens}")

    if usage.completion_tokens >= 4000:  # Threshold set to 4000 as a precaution
        console.print("[bold yellow]Warning:[/bold yellow] Output may be truncated. Attempting to continue the response.")
        continuation_response_text = gpt_sub_agent(prompt, search_query, previous_gpt_tasks, use_search, continuation=True)
        response_text += continuation_response_text

    return response_text

def anthropic_refine(objective, sub_task_results, filename, projectname, continuation=False):
    console.print("\nCalling GPT-4 Turbo to provide the refined final output for your objective:")
    messages = [
        {"role": "system", "content": """You are an expert project finalizer and technical writer. Your task is to review and refine sub-task results into a cohesive final output. You should:

1. Analyze the objective and all sub-task results thoroughly.
2. Synthesize the information into a clear, well-structured final output.
3. Ensure all aspects of the original objective are addressed.
4. Add any missing information or details as needed.
5. For coding projects:
   - Provide a concise and appropriate project name (max 20 characters).
   - Create a detailed folder structure as a valid JSON object.
   - Present each code file with its filename and content in the specified format.
   - Ensure that HTML files are valid and complete, including <!DOCTYPE html>, <html>, <head>, and <body> tags.
6. Maintain consistency in style and formatting throughout the output."""},
        {"role": "user", "content": f"""Objective: {objective}

Sub-task results:
{chr(10).join(sub_task_results)}

Please review and refine the sub-task results into a cohesive final output. Add any missing information or details as needed. 

For coding projects, provide the following:
1. Project Name: Create a concise and appropriate project name that fits the project based on what it's creating. The project name should be no more than 20 characters long.
2. Folder Structure: Provide the folder structure as a valid JSON object, where each key represents a folder or file, and nested keys represent subfolders. Use null values for files. Ensure the JSON is properly formatted without any syntax errors. Please make sure all keys are enclosed in double quotes, and ensure objects are correctly encapsulated with braces, separating items with commas as necessary. Wrap the JSON object in <folder_structure> tags.
3. Code Files: For each code file, include ONLY the file name in the format 'Filename: <filename>' followed by the code block enclosed in triple backticks, with the language identifier after the opening backticks.

Ensure your response is well-structured, clear, and directly addresses the original objective."""}
    ]

    gpt_response = openai_client.chat.completions.create(
        model=REFINER_MODEL,
        messages=messages,
        max_tokens=4096
    )

    response_text = gpt_response.choices[0].message.content.strip()
    logging.debug(f"Raw anthropic_refine output:\n{response_text}")

    # Ensure the response contains the required sections
    if "Project Name:" not in response_text:
        response_text = f"Project Name: {projectname}\n\n" + response_text
    if "<folder_structure>" not in response_text:
        response_text += "\n\n<folder_structure>\n{}\n</folder_structure>"
    if "Filename:" not in response_text:
        response_text += "\n\nFilename: example.html\n```html\n<h1>Example</h1>\n```"

    logging.debug(f"Processed anthropic_refine output:\n{response_text}")

    usage = gpt_response.usage
    console.print(f"Input Tokens: {usage.prompt_tokens}, Output Tokens: {usage.completion_tokens}")

    if usage.completion_tokens >= 4000 and not continuation:  # Threshold set to 4000 as a precaution
        console.print("[bold yellow]Warning:[/bold yellow] Output may be truncated. Attempting to continue the response.")
        continuation_response_text = anthropic_refine(objective, sub_task_results + [response_text], filename, projectname, continuation=True)
        response_text += "\n" + continuation_response_text

    console.print(Panel(response_text, title="[bold green]Final Output[/bold green]", title_align="left", border_style="green"))
    return response_text

def validate_folder_structure(base_path, structure, current_path=''):
    for name, content in structure.items():
        path = os.path.join(current_path, name)
        full_path = os.path.join(base_path, path)
        if content is None:  # It's a file
            if not os.path.isfile(full_path):
                logging.warning(f"Expected file not found: {path}")
        else:  # It's a directory
            if not os.path.isdir(full_path):
                logging.warning(f"Expected directory not found: {path}")
            else:
                validate_folder_structure(base_path, content, path)

def process_objective(objective, file_content, use_search):
    task_exchanges = []
    gpt_tasks = []

    while True:
        previous_results = [result for _, result in task_exchanges]
        if not task_exchanges:
            gpt_result, file_content_for_gpt, search_query = gpt_orchestrator(objective, file_content, previous_results, use_search)
        else:
            gpt_result, _, search_query = gpt_orchestrator(objective, previous_results=previous_results, use_search=use_search)

        if "The task is complete:" in gpt_result:
            final_output = gpt_result.replace("The task is complete:", "").strip()
            break
        else:
            sub_task_prompt = gpt_result
            if file_content_for_gpt and not gpt_tasks:
                sub_task_prompt = f"{sub_task_prompt}\n\nFile content:\n{file_content_for_gpt}"
            sub_task_result = gpt_sub_agent(sub_task_prompt, search_query, gpt_tasks, use_search)
            gpt_tasks.append({"task": sub_task_prompt, "result": sub_task_result})
            task_exchanges.append((sub_task_prompt, sub_task_result))
            file_content_for_gpt = None

    sanitized_objective = sanitize_filename(objective[:50])  # Limit objective length in filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    refined_output = retry_ai_call(anthropic_refine, 3, objective, [result for _, result in task_exchanges], timestamp, sanitized_objective)

    project_name_match = re.search(r'Project Name: (.*)', refined_output)
    project_name = project_name_match.group(1).strip() if project_name_match else sanitized_objective
    project_name = sanitize_filename(project_name)

    # Create the project directory
    project_dir = os.path.join(os.getcwd(), project_name)
    os.makedirs(project_dir, exist_ok=True)

    # Extract folder structure and create directories
    folder_structure_match = re.search(r'<folder_structure>(.*?)</folder_structure>', refined_output, re.DOTALL)
    if folder_structure_match:
        try:
            folder_structure = json.loads(folder_structure_match.group(1))
            create_folder_structure(project_dir, folder_structure)
        except json.JSONDecodeError:
            logging.error("Invalid folder structure JSON")

    # Extract code blocks and create files
    code_blocks = re.findall(r'Filename:\s*`?(\S+)`?\s*```(\w*)\n(.*?)\n```', refined_output, re.DOTALL)
    created_files = []
    for filename, language, content in code_blocks:
        filename = sanitize_filename(filename.strip('`'))
        file_path = os.path.join(project_dir, filename)
        content = content.strip()
        if validate_code(filename, content):
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(content)
                logging.info(f"File created: {file_path}")
                created_files.append(os.path.relpath(file_path, project_dir))
            except Exception as e:
                logging.error(f"Error writing file {filename}: {str(e)}")
        else:
            logging.error(f"Invalid code content for {filename}")

    # Create the log file
    log_filename = f"{timestamp}_{sanitized_objective}.md"
    log_path = os.path.join(project_dir, log_filename)
    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write(f"# Project: {project_name}\n\n")
        log_file.write(f"## Objective\n{objective}\n\n")
        log_file.write("## Task Breakdown\n\n")
        for i, (prompt, result) in enumerate(task_exchanges, start=1):
            log_file.write(f"### Task {i}\n")
            log_file.write(f"**Prompt:** {prompt}\n\n")
            log_file.write(f"**Result:** {result}\n\n")
        log_file.write("## Refined Final Output\n\n")
        log_file.write(refined_output)
        log_file.write("\n\n## Created Files\n\n")
        for created_file in created_files:
            log_file.write(f"- {created_file}\n")

    console.print(f"\n[bold]Project created:[/bold] {project_name}")
    console.print(f"[bold]Files created:[/bold] {', '.join(created_files)}")
    console.print(f"[bold]Log file:[/bold] {log_filename}")

    return {
        'refined_output': refined_output,
        'created_files': created_files,
        'project_name': project_name,
        'log_file': os.path.relpath(log_path, os.getcwd())
    }

def create_folder_structure(base_path, structure):
    for name, content in structure.items():
        path = os.path.join(base_path, name)
        if content is None:  # It's a file
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'a').close()  # Create an empty file
        else:  # It's a directory
            os.makedirs(path, exist_ok=True)
            create_folder_structure(path, content)