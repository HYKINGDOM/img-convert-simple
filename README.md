# 图片监控与重复检测转换器

一个基于 Python 3.12+ 的解决方案，用于监控文件夹中的新图片文件，将其转换为指定格式，并使用 PostgreSQL 数据库和基于哈希的重复检测来防止重复处理。

## 核心功能

- **实时文件监控**：使用 watchdog 监控指定文件夹中的新图片文件
- **图片格式转换**：支持多种格式之间的转换（JPEG、PNG、WebP、BMP、TIFF、GIF、SVG）
- **重复检测**：使用 SHA-256 哈希比较检测并自动删除重复图片
- **数据库集成**：PostgreSQL 数据库存储图片元数据和哈希值
- **线程安全处理**：支持可配置工作线程的并发处理
- **连接池**：高效的数据库连接管理
- **全面日志记录**：详细的彩色日志输出
- **错误处理**：强大的错误处理和恢复机制

## 支持的图片格式

**输入格式**：JPG、JPEG、PNG、GIF、WebP、BMP、SVG、TIFF  
**输出格式**：JPG、PNG、WebP、BMP、TIFF、GIF

## 系统要求

- Python 3.12 或更高版本
- PostgreSQL 数据库
- 虚拟环境（推荐）

## 安装步骤

### 1. 克隆或下载项目

```bash
# 导航到项目目录
cd /path/to/img-convert-simple
```

### 2. 设置虚拟环境

```bash
# 运行设置脚本（推荐）
python setup.py

# 或手动创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 数据库设置

应用程序将在首次运行时自动创建所需的数据库表。确保您的 PostgreSQL 数据库可以使用提供的凭据访问：

- **主机**：10.0.201.34
- **端口**：5432
- **数据库**：user_tZGjBb
- **用户名**：user_tZGjBb
- **密码**：password_fajJed

### 4. 配置

复制示例环境文件并根据需要自定义：

```bash
cp .env.example .env
```

编辑 `.env` 文件以匹配您的要求。

## 使用方法

### 基本用法

```bash
# 首先激活虚拟环境
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# 使用默认设置运行（监控当前目录）
python main.py

# 监控特定目录
python main.py --watch-path "C:\Images\Input"

# 转换为 PNG 格式
python main.py --format png --watch-path "./input_images"

# 多个监控路径
python main.py -w "./folder1" -w "./folder2" -o "./output"
```

### 命令行选项

```bash
python main.py [选项]

选项：
  -w, --watch-path PATH     要监控的目录（可多次使用）
  -o, --output-dir PATH     转换后图片的输出目录
  -f, --format FORMAT       目标格式：jpg、png、webp、bmp、tiff
  -q, --quality INT         JPEG 质量（1-100，默认：85）
  --no-delete              转换后保留原文件
  --no-scan                启动时跳过扫描现有文件
  --workers INT            工作线程数（默认：4）
  --log-level LEVEL        日志级别：DEBUG、INFO、WARNING、ERROR
  
  # 批量处理选项
  --batch-process PATH     批量处理指定文件夹中的所有图片文件
  --no-recursive           批量处理时不递归处理子文件夹
  
  -h, --help               显示帮助信息
```

### 批量处理功能

除了实时监控模式，应用程序还提供批量处理功能，可以一次性处理文件夹中的所有图片文件：

```bash
# 批量处理指定文件夹（递归处理子文件夹）
python main.py --batch-process "./images_folder"

# 批量处理但不递归处理子文件夹
python main.py --batch-process "./images_folder" --no-recursive

# 结合其他选项使用
python main.py --batch-process "./photos" --log-level DEBUG
```

**批量处理功能特点：**
- 遍历指定文件夹中的所有支持格式的图片文件
- 计算每个文件的 SHA-256 哈希值进行去重
- 将非重复文件的元数据插入数据库
- 支持递归处理子文件夹（默认开启）
- 提供详细的处理进度和统计信息
- 不会移动或删除原文件，仅进行数据库记录

### 使用示例

```bash
# 高质量 JPEG 转换并保留原文件
python main.py -w "./photos" -f jpg -q 95 --no-delete

# WebP 转换并指定输出目录
python main.py -w "./input" -o "./webp_output" -f webp

# 调试模式，详细日志
python main.py --log-level DEBUG -w "./test_images"

# 生产环境设置，多工作线程
python main.py -w "./production_input" --workers 8 -f png

# 批量处理现有图片库
python main.py --batch-process "./existing_photos" --log-level INFO
```

## 数据库结构

应用程序创建以下表结构：

```sql
CREATE TABLE image_metadata (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_path TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    file_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 哈希
    image_width INTEGER,
    image_height INTEGER,
    image_format VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    output_path TEXT,
    is_duplicate BOOLEAN DEFAULT FALSE
);

-- 性能索引
CREATE INDEX idx_file_hash ON image_metadata(file_hash);
CREATE INDEX idx_filename ON image_metadata(filename);
CREATE INDEX idx_created_at ON image_metadata(created_at);
```

## 工作原理

1. **文件监控**：应用程序使用 `watchdog` 监控指定目录中的新图片文件
2. **哈希计算**：检测到新文件时，计算文件内容的 SHA-256 哈希值
3. **重复检查**：将哈希值与现有数据库记录进行比较
4. **处理流程**：如果不是重复文件：
   - 将图片元数据存储到 PostgreSQL
   - 将图片转换为目标格式
   - 删除原文件（如果配置了）
   - 更新数据库处理信息
5. **重复处理**：如果检测到重复，自动删除文件

## 配置选项

### 环境变量（.env 文件）

```env
# 数据库
DATABASE_URL=postgresql://user:pass@host:port/dbname

# 应用程序
WATCH_PATHS=./input1,./input2
OUTPUT_DIR=./converted_images
TARGET_FORMAT=jpg
IMAGE_QUALITY=85
DELETE_ORIGINALS=true
SCAN_EXISTING=true
MAX_WORKERS=4

# 日志
LOG_LEVEL=INFO
STATS_INTERVAL=60
```

### 应用程序设置

- **watch_paths**：要监控的目录列表
- **output_dir**：转换后图片的目录
- **target_format**：默认转换格式
- **quality**：JPEG 质量（1-100）
- **delete_originals**：是否删除源文件
- **scan_existing**：启动时扫描现有文件
- **max_workers**：处理线程数

## 日志记录

应用程序提供不同级别的全面日志记录：

- **DEBUG**：详细的处理信息
- **INFO**：一般应用程序流程和统计信息
- **WARNING**：非关键问题（重复文件等）
- **ERROR**：处理错误和失败

日志包括：
- 文件处理状态
- 重复检测结果
- 数据库操作
- 性能统计
- 错误详情

## 性能考虑

- **线程池**：可配置的工作线程数用于并发处理
- **连接池**：数据库连接池提高效率
- **文件就绪检查**：处理前检查文件完整性
- **内存管理**：尽可能使用流模式处理图片
- **批量操作**：优化数据库批量操作

## 错误处理

- **数据库错误**：自动重试和连接恢复
- **文件系统错误**：优雅处理锁定或不可访问的文件
- **图片处理错误**：详细错误日志并保留文件
- **网络问题**：连接超时和重试机制

## 监控和统计

应用程序提供实时统计信息：

```
统计信息 - 运行时间：120.5秒，已处理：45，重复：3，错误：1，数据库总计：150
```

- **运行时间**：应用程序运行时间
- **已处理**：成功转换的图片
- **重复**：检测并删除的重复文件
- **错误**：处理失败
- **数据库总计**：数据库中的图片总数

## 问题修复总结

### 用户反馈的问题及解决方案

#### 问题1：数据库表结构优化
**状态：✅ 已正确实现**

- ✅ **不存储图片源数据** - 符合性能要求
- ✅ **使用 SHA-256 哈希值** - 快速重复检测
- ✅ **实现重复检测功能** - 基于哈希值自动检测

#### 问题2：输出文件夹问题
**状态：✅ 已修复**

**解决方案：**
- 修复了数据库连接问题
- 验证了文件转换功能正常工作
- 确认文件正确输出到配置目录

#### 问题3：源文件删除
**状态：✅ 已正确实现**

- ✅ **配置正确**：`DELETE_ORIGINALS=true`
- ✅ **逻辑实现**：转换成功后自动删除原文件
- ✅ **测试验证**：功能正常工作

### 测试结果

**功能验证测试：**
```
✓ test_image_1.png -> test_image_1.jpg (已处理)
✓ test_image_2.bmp -> test_image_2.jpg (已处理)
✓ test_image_3.webp -> test_image_3.jpg (已处理)

输出目录内容：
  - test_image_1.jpg (541 字节)
  - test_image_2.jpg (540 字节)
  - test_image_3.jpg (541 字节)

输入目录内容（应为空）：
  (空 - 所有文件已处理并删除)
```

**数据库功能验证：**
- ✅ 哈希值计算和存储
- ✅ 重复文件检测
- ✅ 元数据记录（不包含图片源数据）
- ✅ 处理状态跟踪

## 故障排除

### 常见问题

1. **数据库连接失败**
   ```
   ERROR - Failed to initialize database engine
   ```
   - 检查数据库凭据和网络连接
   - 验证 PostgreSQL 服务是否运行
   - 手动测试连接

2. **权限错误**
   ```
   ERROR - Failed to delete original file: Permission denied
   ```
   - 检查文件权限
   - 确保应用程序对目录有写入权限
   - 使用适当权限运行

3. **图片处理错误**
   ```
   ERROR - Failed to convert image: Unsupported format
   ```
   - 验证输入文件是有效图片
   - 检查格式是否支持
   - 确保文件未损坏

### 调试模式

使用调试日志获取详细信息：

```bash
python main.py --log-level DEBUG
```

### 数据库检查

连接到 PostgreSQL 检查数据：

```sql
-- 检查图片统计
SELECT 
    COUNT(*) as total_images,
    COUNT(CASE WHEN processed_at IS NOT NULL THEN 1 END) as processed,
    COUNT(CASE WHEN is_duplicate THEN 1 END) as duplicates
FROM image_metadata;

-- 查看最近图片
SELECT filename, image_format, file_size, created_at, processed_at
FROM image_metadata
ORDER BY created_at DESC
LIMIT 10;
```

## 开发

### 项目结构

```
img-convert-simple/
├── main.py              # 主应用程序入口
├── database.py          # 数据库操作和模型
├── image_processor.py   # 图片转换和处理
├── file_monitor.py      # 文件系统监控
├── setup.py            # 环境设置脚本
├── requirements.txt    # Python 依赖
├── .env.example       # 环境配置模板
└── README.md          # 本文件
```

### 测试

测试各个组件：

```bash
# 测试数据库连接
python database.py

# 测试图片处理器
python image_processor.py

# 测试文件监控
python file_monitor.py
```

### 测试文件

- `test_local.py` - 本地 SQLite 测试脚本
- `test_image_creation.py` - 测试图片生成脚本
- `demo.py` - 交互式演示脚本

### 贡献指南

1. 遵循 PEP 8 风格指南
2. 添加全面的日志记录
3. 包含错误处理
4. 更新文档
5. 充分测试

## 使用建议

1. **确保数据库连接可用** - 检查 PostgreSQL 服务器连接
2. **使用正确的命令行参数**：
   ```bash
   python main.py --watch-path ./input_folder --output-dir D:\converted_images
   ```
3. **检查配置文件** - 确保 `.env` 文件中的设置正确
4. **监控日志输出** - 应用程序提供详细的处理日志

## 许可证

本项目仅供教育和开发目的使用。

## 支持

如有问题和疑问：
1. 查看故障排除部分
2. 启用调试日志
3. 查看应用程序日志
4. 验证数据库连接