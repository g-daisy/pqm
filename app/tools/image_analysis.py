from base import BaseTool

#规划功能，暂时没用
class Image_analysis_tool():
    @property
    def name(self) -> str:
        return "image_analysis"

    @property
    def description(self) -> str:
        return "识别用户上传的图片，分析图中是属于什么缺陷"

    @property
    def input_schema(self) -> dict:
        return {
            "type" : "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户的问题，例如：热压工序出现暗裂的原因是什么？",
                },
                "session_id": {
                    "type": "string",
                    "description": "会话 ID，用于追问改写",
                    "default": "default",
                },
            },
            "required": ["question"],
        }

    async def run(self, *, question: str, session_id: str = "default") -> dict:
        pass