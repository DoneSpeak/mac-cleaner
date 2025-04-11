.PHONY: install uninstall clean build dev-install help check-deps check

# 默认目标
.DEFAULT_GOAL := help

# 颜色设置
BLUE=\033[0;34m
GREEN=\033[0;32m
RED=\033[0;31m
YELLOW=\033[1;33m
NC=\033[0m # No Color

help:
	@echo "${BLUE}MacCleaner Makefile Help${NC}"
	@echo ""
	@echo "${GREEN}Available targets:${NC}"
	@echo "  ${YELLOW}install${NC}      - Install MacCleaner to the system (will overwrite existing installation)"
	@echo "  ${YELLOW}dev-install${NC}  - Install MacCleaner in development mode (editable)"
	@echo "  ${YELLOW}uninstall${NC}    - Remove MacCleaner from the system"
	@echo "  ${YELLOW}build${NC}        - Build distribution packages"
	@echo "  ${YELLOW}clean${NC}        - Remove build artifacts"
	@echo "  ${YELLOW}check${NC}        - Check environment configuration"
	@echo ""
	@echo "${GREEN}Usage examples:${NC}"
	@echo "  make install        # Install or reinstall MacCleaner"
	@echo "  make install USER=1 # Install for current user only (no sudo)"
	@echo ""

# 检查依赖工具
check-deps:
	@which pip > /dev/null || (echo "${RED}Error: pip is not installed. Please install Python and pip first.${NC}" && exit 1)
	@which poetry > /dev/null 2>&1 || (echo "${YELLOW}Warning: Poetry is not installed. Installing using pip...${NC}" && pip install poetry)

# 检查环境配置
check: check-deps
	@echo "${BLUE}Checking environment configuration...${NC}"
	@echo "Python version: $$(python --version)"
	@echo "Pip version: $$(pip --version)"
	@echo "Poetry version: $$(poetry --version)"
	@echo "${GREEN}Environment check complete!${NC}"
	@echo ""
	@echo "${BLUE}Checking project configuration...${NC}"
	@if [ -f "pyproject.toml" ]; then \
		echo "${GREEN}✓${NC} pyproject.toml exists"; \
	else \
		echo "${RED}✗${NC} pyproject.toml not found"; \
		exit 1; \
	fi
	@echo "${GREEN}Project check complete!${NC}"

# 构建软件包
build: check-deps
	@echo "${BLUE}Building package using Poetry...${NC}"
	poetry build

# 安装软件包（如果已存在则覆盖）
install: build
	@echo "${BLUE}Installing MacCleaner...${NC}"
	@if [ "$(USER)" = "1" ]; then \
		pip install --force-reinstall dist/*.whl --user; \
		echo "${YELLOW}NOTE: The maccleaner command might be installed in a user-specific bin directory.${NC}"; \
		echo "${YELLOW}If you cannot run it, add this to your PATH:${NC}"; \
		echo "${YELLOW}  export PATH=\"\$$PATH:\$$(python3 -m site --user-base)/bin\"${NC}"; \
	else \
		pip install --force-reinstall dist/*.whl; \
	fi
	@echo "${GREEN}Installation complete!${NC}"
	@echo "You can now use MacCleaner by running 'maccleaner' command."
	@echo ""
	@echo "${BLUE}Verifying installation...${NC}"
	@MACCLEANER_PATH=$$(which maccleaner 2>/dev/null || echo "NOT_FOUND"); \
	if [ "$$MACCLEANER_PATH" = "NOT_FOUND" ]; then \
		echo "${YELLOW}Warning: maccleaner command not found in PATH.${NC}"; \
		echo "${YELLOW}Try running it with the full path or add the installation directory to your PATH.${NC}"; \
		PYTHON_USER_BIN=$$(python3 -m site --user-base)/bin; \
		if [ -f "$${PYTHON_USER_BIN}/maccleaner" ]; then \
			echo "${GREEN}Found at: $${PYTHON_USER_BIN}/maccleaner${NC}"; \
			echo "${YELLOW}To use it, run: $${PYTHON_USER_BIN}/maccleaner${NC}"; \
			echo "${YELLOW}Or add to PATH: export PATH=\"\$$PATH:$${PYTHON_USER_BIN}\"${NC}"; \
		fi; \
	else \
		echo "${GREEN}Found maccleaner at: $$MACCLEANER_PATH${NC}"; \
		python3 -c "import sys; from maccleaner.cli import main; sys.exit(main(['--version']))"; \
	fi

# 使用Poetry进行开发模式安装
dev-install: check-deps
	@echo "${BLUE}Installing MacCleaner in development mode using Poetry...${NC}"
	@if [ "$(USER)" = "1" ]; then \
		poetry install --no-root; \
		pip install -e . --user; \
	else \
		poetry install; \
	fi
	@echo "${GREEN}Dev installation complete!${NC}"

# 卸载软件包
uninstall: check-deps
	@echo "${BLUE}Uninstalling MacCleaner...${NC}"
	pip uninstall -y maccleaner
	@echo "${GREEN}Uninstallation complete!${NC}"

# 清理构建产物
clean:
	@echo "${BLUE}Cleaning build artifacts...${NC}"
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "${GREEN}Cleanup complete!${NC}" 