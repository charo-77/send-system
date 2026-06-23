from __future__ import annotations

STATE_TEXT = {
    'INIT': '准备启动',
    'LAUNCHING': '正在打开浏览器',
    'EDITOR_READY': '编辑器已就绪',
    'DOC_IMPORTING': '正在导入文档',
    'DOC_IMPORTED': '文档已导入',
    'COVER_PROCESSING': '正在处理封面',
    'COVER_DONE': '封面已处理',
    'WAIT_MANUAL_CAPTCHA': '等待人工完成百度验证',
    'READY_TO_SUBMIT': '准备发布',
    'SUBMITTING': '正在提交发布',
    'SUCCESS': '发布成功',
    'FAILED': '发布失败',
    'STUCK': '页面卡住',
}


def cn_state(name: str) -> str:
    return STATE_TEXT.get(name, name)
