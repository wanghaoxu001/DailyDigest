#!/usr/bin/env python3
"""
Python 版本性能对比测试脚本
用于测试不同 Python 版本的性能差异
"""

import time
import sys
import asyncio
import json
from typing import List, Dict, Any
import psutil
import os


class PerformanceBenchmark:
    """性能基准测试类"""
    
    def __init__(self):
        self.results = {}
        self.process = psutil.Process()
        
    def measure_time(self, func_name: str):
        """装饰器：测量函数执行时间"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                start_memory = self.process.memory_info().rss
                
                result = func(*args, **kwargs)
                
                end_time = time.perf_counter()
                end_memory = self.process.memory_info().rss
                
                execution_time = end_time - start_time
                memory_diff = end_memory - start_memory
                
                self.results[func_name] = {
                    'execution_time': execution_time,
                    'memory_usage': memory_diff,
                    'memory_start': start_memory,
                    'memory_end': end_memory
                }
                
                print(f"✅ {func_name}: {execution_time:.4f}秒, 内存变化: {memory_diff/1024/1024:.2f}MB")
                return result
            return wrapper
        return decorator
    
    async def measure_async_time(self, func_name: str, func, *args, **kwargs):
        """异步函数时间测量"""
        start_time = time.perf_counter()
        start_memory = self.process.memory_info().rss
        
        result = await func(*args, **kwargs)
        
        end_time = time.perf_counter()
        end_memory = self.process.memory_info().rss
        
        execution_time = end_time - start_time
        memory_diff = end_memory - start_memory
        
        self.results[func_name] = {
            'execution_time': execution_time,
            'memory_usage': memory_diff,
            'memory_start': start_memory,
            'memory_end': end_memory
        }
        
        print(f"✅ {func_name}: {execution_time:.4f}秒, 内存变化: {memory_diff/1024/1024:.2f}MB")
        return result


def run_cpu_intensive_test(benchmark: PerformanceBenchmark):
    """CPU密集型测试"""
    @benchmark.measure_time("CPU密集型计算")
    def cpu_test():
        # 计算质数
        def is_prime(n):
            if n < 2:
                return False
            for i in range(2, int(n**0.5) + 1):
                if n % i == 0:
                    return False
            return True
        
        primes = [n for n in range(2, 10000) if is_prime(n)]
        return len(primes)
    
    result = cpu_test()
    print(f"找到质数数量: {result}")


def run_data_processing_test(benchmark: PerformanceBenchmark):
    """数据处理测试"""
    @benchmark.measure_time("大数据列表处理")
    def data_processing():
        # 模拟新闻数据处理
        data = [
            {
                'id': i,
                'title': f'新闻标题 {i}',
                'content': f'这是第{i}条新闻的内容' * 10,
                'tags': [f'tag{j}' for j in range(5)],
                'score': i * 0.1
            }
            for i in range(50000)
        ]
        
        # 数据处理操作
        filtered_data = [
            item for item in data 
            if item['score'] > 100 and len(item['content']) > 50
        ]
        
        processed_data = [
            {
                'id': item['id'],
                'title': item['title'].upper(),
                'summary': item['content'][:100],
                'tag_count': len(item['tags'])
            }
            for item in filtered_data
        ]
        
        return len(processed_data)
    
    result = data_processing()
    print(f"处理后数据量: {result}")


async def run_async_test(benchmark: PerformanceBenchmark):
    """异步处理测试"""
    async def async_task(n: int) -> Dict[str, Any]:
        # 模拟异步I/O操作
        await asyncio.sleep(0.001)
        return {
            'task_id': n,
            'result': n ** 2,
            'processed_at': time.time()
        }
    
    async def async_processing():
        # 模拟并发处理多个任务
        tasks = [async_task(i) for i in range(1000)]
        results = await asyncio.gather(*tasks)
        return len(results)
    
    result = await benchmark.measure_async_time(
        "异步并发处理", 
        async_processing
    )
    print(f"异步任务完成数量: {result}")


def run_json_processing_test(benchmark: PerformanceBenchmark):
    """JSON处理测试"""
    @benchmark.measure_time("JSON序列化反序列化")
    def json_test():
        # 创建复杂的嵌套数据结构
        complex_data = {
            'news_list': [
                {
                    'id': i,
                    'title': f'标题 {i}',
                    'content': f'内容 {i}' * 100,
                    'metadata': {
                        'author': f'作者 {i}',
                        'tags': [f'tag{j}' for j in range(10)],
                        'created_at': time.time(),
                        'stats': {
                            'views': i * 10,
                            'likes': i * 2,
                            'shares': i
                        }
                    }
                }
                for i in range(5000)
            ]
        }
        
        # JSON序列化和反序列化
        json_str = json.dumps(complex_data, ensure_ascii=False)
        parsed_data = json.loads(json_str)
        
        return len(parsed_data['news_list'])
    
    result = json_test()
    print(f"JSON处理数据量: {result}")


def run_string_processing_test(benchmark: PerformanceBenchmark):
    """字符串处理测试"""
    @benchmark.measure_time("字符串处理")
    def string_test():
        # 模拟文本处理
        texts = [f'这是一段很长的文本内容，包含了各种中文字符和标点符号。第{i}段。' * 50 for i in range(10000)]
        
        processed_texts = []
        for text in texts:
            # 文本处理操作
            processed = text.upper().replace('。', '!')
            processed = ''.join(char for char in processed if char.isalnum() or char in '!，')
            processed_texts.append(processed[:200])  # 截取前200字符
        
        return len(processed_texts)
    
    result = string_test()
    print(f"字符串处理数量: {result}")


def print_system_info():
    """打印系统信息"""
    print("🖥️ 系统信息")
    print("=" * 50)
    print(f"Python版本: {sys.version}")
    print(f"操作系统: {os.name}")
    print(f"CPU核心数: {psutil.cpu_count()}")
    print(f"可用内存: {psutil.virtual_memory().total / 1024**3:.1f} GB")
    print(f"当前内存使用: {psutil.virtual_memory().percent}%")
    print("=" * 50)
    print()


def print_results(benchmark: PerformanceBenchmark):
    """打印测试结果"""
    print("\n📊 性能测试结果汇总")
    print("=" * 70)
    print(f"{'测试项目':<20} {'执行时间(秒)':<15} {'内存使用(MB)':<15}")
    print("-" * 70)
    
    total_time = 0
    total_memory = 0
    
    for test_name, result in benchmark.results.items():
        exec_time = result['execution_time']
        memory_mb = result['memory_usage'] / 1024 / 1024
        
        print(f"{test_name:<20} {exec_time:<15.4f} {memory_mb:<15.2f}")
        
        total_time += exec_time
        total_memory += abs(memory_mb)
    
    print("-" * 70)
    print(f"{'总计':<20} {total_time:<15.4f} {total_memory:<15.2f}")
    print("=" * 70)
    
    # 生成性能报告JSON
    report = {
        'python_version': sys.version,
        'test_timestamp': time.time(),
        'system_info': {
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / 1024**3,
            'os_name': os.name
        },
        'test_results': benchmark.results,
        'summary': {
            'total_execution_time': total_time,
            'total_memory_usage_mb': total_memory
        }
    }
    
    # 保存报告
    report_file = f"performance_report_py{sys.version_info.major}.{sys.version_info.minor}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 详细报告已保存到: {report_file}")


async def main():
    """主函数"""
    print("🚀 Python 性能基准测试")
    print("=" * 50)
    
    print_system_info()
    
    benchmark = PerformanceBenchmark()
    
    print("🔄 开始性能测试...")
    print()
    
    # 运行各项测试
    run_cpu_intensive_test(benchmark)
    run_data_processing_test(benchmark)
    run_string_processing_test(benchmark)
    run_json_processing_test(benchmark)
    await run_async_test(benchmark)
    
    # 打印结果
    print_results(benchmark)
    
    print("\n✅ 所有测试完成！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc() 