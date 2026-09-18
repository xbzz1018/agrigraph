"""兼容 ``python -m app.reset_password`` 的本地账号恢复入口。"""

from app.cli.reset_password import main

if __name__ == "__main__":
    main()
