import json
import os
import random
import time
import sqlite3
import Get_informations.GetScore as GetScore
import Get_informations.Get_province_id as Get_Province_Id
import Get_informations.Get_school_id as Get_School_Id

# 创建或连接到进度数据库
def init_progress_db():
    conn = sqlite3.connect('progress.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS progress
                     (task_id TEXT PRIMARY KEY, 
                      province_id TEXT,
                      want TEXT,
                      year INTEGER,
                      rank INTEGER,
                      processed_schools TEXT,
                      results TEXT)''')
    conn.commit()
    return conn

# 主处理函数
def process(province_id, want, year, thread_num, ethnic_minority, output, rank, schools=None):
    # 初始化进度数据库
    progress_conn = init_progress_db()
    progress_cursor = progress_conn.cursor()

    # 创建任务ID（包含指定院校信息）
    schools_key = "_".join(sorted(schools)) if schools else "all"
    task_id = f"{province_id}_{want}_{year}_{rank}_{schools_key}"

    # 检查是否有之前的进度
    progress_cursor.execute('''SELECT processed_schools, results FROM progress WHERE task_id = ?''', (task_id,))
    result = progress_cursor.fetchone()

    if result:
        processed_schools = set(json.loads(result[0]))
        existing_results = json.loads(result[1])
        print(f"发现之前进度，已处理 {len(processed_schools)} 所学校")
    else:
        processed_schools = set()
        existing_results = []

    # 获取省份ID和学校列表
    province_id = str(province_id)
    province_id = Get_Province_Id.get_province_id(province_id)
    all_school_id = Get_School_Id.get_school_ids()

    # 如果指定了院校列表，只保留匹配的学校（模糊匹配）
    if schools:
        filtered_school_id = {}
        for school_name, school_id in all_school_id.items():
            for target in schools:
                if target in school_name:
                    filtered_school_id[school_name] = school_id
                    break
        all_school_id = filtered_school_id
        print(f"指定院校匹配到 {len(all_school_id)} 所学校:")
        for name in all_school_id:
            print(f"  - {name}")

    # 过滤掉已处理的学校
    schools_to_process = {k: v for k, v in all_school_id.items() if k not in processed_schools}
    
    if not schools_to_process:
        print("所有学校已处理完成")
        # 删除进度记录
        progress_cursor.execute('''DELETE FROM progress WHERE task_id = ?''', (task_id,))
        progress_conn.commit()
        progress_conn.close()
        
        if output:
            # 保存最终结果
            path = os.getcwd()
            output_file = f"{path}/{year}_{want}_学校分数排行.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(existing_results, f, ensure_ascii=False, indent=4)
            return f"所有学校已处理完成，结果已保存到 {output_file}"
        else:
            return existing_results
    
    results = existing_results
    times = 0
    
    print(f"开始处理 {len(schools_to_process)} 所学校...")
    
    # 顺序处理每个学校
    for school_name, school_id in list(schools_to_process.items()):
        try:
            print(f"正在处理 {school_name}")
            
            # 跳过特定类型的学校
            if "学院" in school_name or "职业" in school_name:
                processed_schools.add(school_name)
                # 更新进度
                progress_cursor.execute('''INSERT OR REPLACE INTO progress 
                                        (task_id, province_id, want, year, rank, processed_schools, results) 
                                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                        (task_id, province_id, want, year, rank, 
                                         json.dumps(list(processed_schools)), json.dumps(results)))
                progress_conn.commit()
                continue
                
            # 获取学校数据
            all_score = GetScore.getScore(schoolId=school_id, provinceId=province_id, year=year)
            majors = all_score.get("item", [])
            
            # 处理专业数据
            school_results = []
            for major in majors:
                # 确保min_section是数字
                min_section = major.get("min_section", 0)
                if isinstance(min_section, str):
                    try:
                        min_section = int(min_section)
                    except ValueError:
                        continue
                
                # 检查专业条件
                if (want in major["spname"] and 
                    ("专项" in major["spname"] or not ethnic_minority) and 
                    abs(min_section - rank) < 3000):
                    school_results.append({major["spname"]: {"min": major["min"], "min_section": major["min_section"]}})
            
            # 如果有匹配的专业，添加到结果中
            if school_results:
                results.append({school_name: school_results})
                print(f"找到匹配专业: {school_name}")
            
            # 更新进度
            processed_schools.add(school_name)
            progress_cursor.execute('''INSERT OR REPLACE INTO progress 
                                    (task_id, province_id, want, year, rank, processed_schools, results) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                    (task_id, province_id, want, year, rank, 
                                     json.dumps(list(processed_schools)), json.dumps(results)))
            progress_conn.commit()
            
            # 控制请求频率
            times += 1
            if times % 10 == 0:
                print("处理了10所学校，暂停30秒...")
                time.sleep(30)
            else:
                time.sleep(random.uniform(0.1, 0.3))
                
        except Exception as e:
            print(f"处理学校 {school_name} 时出错: {e}")
            print("暂停10分钟后再继续...")
            
            # 不更新进度，保持当前状态
            # 等待10分钟
            for i in range(600, 0, -10):
                if i % 60 == 0:
                    print(f"等待 {i//60} 分钟 {i%60} 秒...")
                else:
                    print(f"等待 {i} 秒...")
                time.sleep(10)
            
            print("继续处理...")
            schools_to_process[school_name] = school_id
    
    # 任务完成，删除进度记录
    progress_cursor.execute('''DELETE FROM progress WHERE task_id = ?''', (task_id,))
    progress_conn.commit()
    progress_conn.close()
    
    if output:
        # 保存结果
        path = os.getcwd()
        output_file = f"{path}/{year}_{want}_学校分数排行.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        return f"已将结果保存到 {output_file}，共处理 {len(results)} 所学校"
    else:
        return results