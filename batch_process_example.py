#!/usr/bin/env python3
"""
批量处理功能使用示例
演示如何使用ImageDuplicateDetector的batch_process_folder方法
"""

import os
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import ImageDuplicateDetector, load_config, setup_logging, initialize_database

def example_batch_process():
    """批量处理功能使用示例"""
    
    # 设置日志
    setup_logging('INFO')
    
    # 加载配置
    config = load_config()
    
    # 创建应用实例
    app = ImageDuplicateDetector(config)
    
    # 初始化数据库
    if not initialize_database():
        print("数据库初始化失败")
        return False
    
    try:
        # 示例1: 处理test_input文件夹（递归）
        test_folder = "./test_input"
        if Path(test_folder).exists():
            print(f"\n=== 示例1: 递归处理 {test_folder} ===")
            result = app.batch_process_folder(test_folder, recursive=True)
            print(f"处理结果: {result}")
        
        # 示例2: 处理指定文件夹（非递归）
        # 你可以修改这个路径为你想要处理的文件夹
        custom_folder = "./test_images"  # 修改为你的图片文件夹路径
        if Path(custom_folder).exists():
            print(f"\n=== 示例2: 非递归处理 {custom_folder} ===")
            result = app.batch_process_folder(custom_folder, recursive=False)
            print(f"处理结果: {result}")
        else:
            print(f"\n注意: 文件夹 {custom_folder} 不存在，跳过示例2")
            print("你可以修改 custom_folder 变量为你想要处理的文件夹路径")
        
        return True
        
    except Exception as e:
        print(f"批量处理过程中发生错误: {e}")
        return False
    
    finally:
        # 清理资源
        app.stop()

def main():
    """主函数"""
    print("=== 图片批量处理功能演示 ===")
    print("此脚本演示如何使用批量处理功能")
    print("功能: 遍历文件夹中的所有图片文件，计算hash去重后插入数据库")
    print("\n支持的图片格式: jpg, jpeg, png, gif, bmp, tiff, webp")
    print("\n开始演示...\n")
    
    success = example_batch_process()
    
    if success:
        print("\n=== 演示完成 ===")
        print("\n使用方法:")
        print("1. 命令行方式:")
        print("   python main.py --batch-process /path/to/your/images")
        print("   python main.py --batch-process /path/to/your/images --no-recursive")
        print("\n2. 代码方式:")
        print("   app = ImageDuplicateDetector(config)")
        print("   result = app.batch_process_folder('/path/to/images', recursive=True)")
    else:
        print("\n=== 演示失败 ===")
        print("请检查错误信息并确保数据库配置正确")
        sys.exit(1)

if __name__ == "__main__":
    main()