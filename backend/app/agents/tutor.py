from .assistant import ask

async def tutor(user_id:str,project_id:str,question:str,thread_id:str|None=None,current_code:str|None=None,file_path:str|None=None,hint_level:int=1,allow_final_answer:bool=False):
    return await ask(user_id=user_id,project_id=project_id,question=question,thread_id=thread_id,mode='socratic',current_code=current_code,file_path=file_path,hint_level=hint_level,allow_final_answer=allow_final_answer)
