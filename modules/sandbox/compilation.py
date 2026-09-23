import ast
import linecache
import traceback

def execute_rhombus_code(code_blocks: list[str], target_name: str | None) -> list[tuple[str, str]]:
    import rhombus
    namespace = {
        'rhombus': rhombus,
        **{name: getattr(rhombus, name) for name in dir(rhombus) if not name.startswith('_')}
    }
    
    for i, block in enumerate(code_blocks):
        block_name = f'<Code Block {i+1}>'
        linecache.cache[block_name] = (len(block), None, [line + '\n' for line in block.splitlines()], block_name)
        
        if i == len(code_blocks) - 1 and target_name is None:
            tree = ast.parse(block)
            if not tree.body:
                raise ValueError(f'Der Code-Block {i+1} ist leer.')
            
            last_node = tree.body[-1]
            if isinstance(last_node, ast.Expr):
                tree.body.pop()
                exec(compile(tree, filename=block_name, mode='exec'), namespace)
                target_value = eval(compile(ast.Expression(last_node.value), filename=block_name, mode='eval'), namespace)
                target_name = '<unbound expression>'
                target_var = rhombus.Density(target_value)
            else:
                raise ValueError('Es wurde kein target angegeben und der Code endet nicht mit einer Expression.')
        else:
            exec(compile(block, filename=block_name, mode='exec'), namespace)

    if target_name is not None and target_name != '<unbound expression>':
        if target_name not in namespace:
            raise ValueError(f'Variable {target_name} is not defined.')
        target_var = rhombus.Density(namespace[target_name])
        
    files = target_var.compile()
    
    files_data = []
    for identifier, beet_file in files:
        content_str = beet_file.encoder(beet_file.data)
        filename = identifier.split(':')[0] + '/' + '/'.join(beet_file.scope) + '/' + identifier.split(':')[-1] + beet_file.extension
        files_data.append((filename, content_str))
        
    return files_data