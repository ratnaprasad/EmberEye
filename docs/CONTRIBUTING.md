# Contributing to EmberEye

Thank you for your interest in contributing to EmberEye! We welcome contributions from the community.

## Getting Started

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/EmberEye.git`
3. **Create a branch**: `git checkout -b feature/your-feature-name`
4. **Make changes** and commit: `git commit -m "Add your feature"`
5. **Push** to your fork: `git push origin feature/your-feature-name`
6. **Create a Pull Request** to the main repository

## Development Setup

```bash
# Clone and setup
git clone https://github.com/ratnaprasad/EmberEye.git
cd EmberEye

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python main.py
```

## Code Style

- Follow PEP 8 guidelines
- Use meaningful variable/function names
- Add docstrings to functions
- Keep functions focused and small
- Add comments for complex logic

## Testing

```bash
# Run tests
cd tests/
python -m pytest

# Run individual test
python test_your_test.py
```

## Reporting Issues

- Check if the issue already exists
- Include Python version, OS, and error traceback
- Provide steps to reproduce
- Attach logs if available (check `setup_log_*.txt` or `setup_errors_*.txt`)

## Pull Request Guidelines

- One feature per PR
- Update tests if changing functionality
- Update documentation if needed
- Reference any related issues
- Provide clear PR description

## Areas for Contribution

- 🐛 **Bug fixes** - Report and fix issues
- ✨ **Features** - New camera integrations, UI improvements, algorithms
- 📖 **Documentation** - Improve guides, add examples
- 🧪 **Tests** - Add/improve test coverage
- 🎨 **UI/UX** - Design improvements

## License

By contributing, you agree your contributions will be licensed under MIT License.

## Questions?

- Open an issue for discussion
- Check existing documentation
- Join our community discussions

Happy contributing! 🚀
