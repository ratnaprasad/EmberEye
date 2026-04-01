"""Show torch init DLL loading section."""
torch_init = "D:/EE/EmberEye-develop-2.x/.venv/Lib/site-packages/torch/__init__.py"
with open(torch_init, encoding="utf-8") as f:
    lines = f.readlines()
for i in range(162, 290):  # _load_dll_libraries function context
    print(f"{i+1:4d}: {lines[i]}", end="")
