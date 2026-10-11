"""Compatibility entry point: validate only; never overwrite the expanded bank."""
from validate_bank import main

if __name__ == '__main__':
    print('旧示例生成器已停用；现在只检查题库，不写入任何文件。')
    main()
