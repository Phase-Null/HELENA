# task_processor.py

import subprocess
import json

class TaskProcessor:
    def __init__(self):
        pass

    def chat_integration(self, message):
        # Simulate chat message processing
        response = f"Chat response to: {message}"
        return response

    def generate_code(self, language, task_description):
        # Placeholder for code generation logic
        generated_code = f"# {task_description}\n\nprint('Hello, World!')"
        return generated_code

    def debug_code(self, code):
        # Simulate debugging logic
        debugged_code = code.replace('print', 'print_debug')
        return debugged_code

    def optimize_code(self, code):
        # Placeholder for code optimization logic
        optimized_code = code.replace('  ', ' ').replace('print', 'print()')
        return optimized_code

    def execute_command(self, command):
        # Execute a system command and return the output
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, check=True)
            return result.stdout.decode('utf-8')
        except subprocess.CalledProcessError as e:
            return json.dumps({"error": e.stderr.decode('utf-8')})

# Example usage (commented out for module safety)
# if __name__ == "__main__":
#     processor = TaskProcessor()
#     print(processor.chat_integration("Hello!"))
#     print(processor.generate_code("Python", "simple greeting app"))
#     print(processor.debug_code("print('This is a test')"))
#     print(processor.optimize_code("print  ('Optimized code')"))
#     print(processor.execute_command("echo 'Hello, World!'"))
