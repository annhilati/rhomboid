import ast
import linecache
import traceback

def execute_rhombus_code(code_blocks: list[str]) -> list[tuple[str, str]]:
    import rhombus
    namespace = {
        '__name__': '__main__',
        'rhombus': rhombus,
        **{name: getattr(rhombus, name) for name in dir(rhombus) if not name.startswith('_')}
    }
    
    merged_code = "\n".join(code_blocks)
    tree = ast.parse(merged_code)
    if not tree.body:
        raise ValueError("The code blocks are empty.")
        
    lines = merged_code.splitlines()
    
    last_node = tree.body[-1]
    if not isinstance(last_node, ast.Expr):
        raise ValueError("Code must end with an unbound expression that contains the Density to compile.")
        
    start_line = last_node.lineno - 1
    stripped = lines[start_line].lstrip()
    indent = lines[start_line][:len(lines[start_line]) - len(stripped)]
    lines[start_line] = indent + "return " + stripped
        
    wrapped_source = "@rhombus.macro\ndef rhombus_code():\n"
    for line in lines:
        wrapped_source += "    " + line + "\n"
        
    block_name = "<Code Blocks>"
    linecache.cache[block_name] = (len(wrapped_source), None, [line + '\n' for line in wrapped_source.splitlines()], block_name)
    
    exec(compile(wrapped_source, filename=block_name, mode='exec'), namespace)
    
    user_code_func = namespace['rhombus_code']
    result = user_code_func()
    
    target_var = rhombus.Density(result)
        
    files = target_var.compile()
    
    files_data = []
    for identifier, beet_file in files:
        content_str = beet_file.encoder(beet_file.data)
        filename = identifier.split(':')[0] + '/' + '/'.join(beet_file.scope) + '/' + identifier.split(':')[-1] + beet_file.extension
        files_data.append((filename, content_str))
        
    return files_data