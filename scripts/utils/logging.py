"""
结构化日志配置模块 (Logging)

基于 structlog 提供双格式日志输出（终端 logfmt / 文件 JSONL）。
所有 Skill 脚本应统一使用此模块初始化日志，禁止直接使用 print() 或标准 logging。
"""
from pathlib import Path
import structlog
import logging
import sys

def setup_logging(logfile: str = "", project_root: Path | None = None):
    """
    配置 structlog 日志 - 终端 logfmt / 文件 JSONL

    Args:
        logfile: 日志文件路径。空字符串输出到终端，指定路径输出到文件。
                 相对路径将相对于 project_root 解析。
        project_root: 项目根目录。未提供时自动向上推算至 skills/ 目录。
    """
    if project_root is None:
        # 从当前模块 (utils/logging.py) 向上推算至项目根目录 (skills/)
        project_root = Path(__file__).resolve().parent.parent.parent.parent

    shared_processors = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if logfile:
        renderer = structlog.processors.JSONRenderer()
        log_path = Path(logfile)
        if not log_path.is_absolute():
            log_path = project_root / logfile
            log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(log_path), encoding="utf-8")
    else:
        renderer = structlog.processors.LogfmtRenderer()
        handler = logging.StreamHandler(sys.stdout)

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    handler.setFormatter(formatter)

    # 清除现有 handlers 防止重复添加
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers.clear()

    logging.basicConfig(handlers=[handler], level=logging.INFO, format="%(message)s")

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

# 预定义 logger 实例，供各模块直接导入使用
logger = structlog.get_logger()
