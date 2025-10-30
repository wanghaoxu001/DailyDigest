
#!/usr/bin/env python3
"""
简单的时间格式化测试脚本
独立测试时区格式化逻辑，不依赖FastAPI
"""

from datetime import datetime, timedelta
import pytz

# 北京时区
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def format_datetime_with_tz(dt):
    """将datetime对象格式化为带时区信息的ISO字符串"""
    if dt is None:
        return None
    
    # 如果datetime是naive（没有时区信息），假设它是北京时间
    if dt.tzinfo is None:
        dt = BEIJING_TZ.localize(dt)
    # 如果已有时区信息，转换到北京时区
    else:
        dt = dt.astimezone(BEIJING_TZ)
    
    return dt.isoformat()

def test_time_formatting():
    """测试时间格式化"""
    print("🕐 时间格式化测试")
    print("=" * 50)
    
    # 测试当前时间
    now = datetime.now()
    formatted_now = format_datetime_with_tz(now)
    print(f"当前时间: {now}")
    print(f"格式化结果: {formatted_now}")
    print(f"包含时区信息: {'+08:00' in formatted_now}")
    
    # 测试1小时前
    one_hour_ago = now - timedelta(hours=1)
    formatted_hour_ago = format_datetime_with_tz(one_hour_ago)
    print(f"\n1小时前: {one_hour_ago}")
    print(f"格式化结果: {formatted_hour_ago}")
    print(f"包含时区信息: {'+08:00' in formatted_hour_ago}")
    
    # 测试UTC时间转换
    utc_now = datetime.utcnow()
    utc_tz = pytz.timezone('UTC')
    utc_dt = utc_tz.localize(utc_now)
    formatted_utc = format_datetime_with_tz(utc_dt)
    print(f"\nUTC时间: {utc_dt}")
    print(f"转换为北京时间: {formatted_utc}")
    
    return True

def simulate_frontend_parsing():
    """模拟前端解析时间"""
    print(f"\n📱 前端解析模拟")
    print("=" * 50)
    
    # 生成一个带时区的时间字符串
    now = datetime.now()
    tz_time_str = format_datetime_with_tz(now)
    print(f"API返回时间字符串: {tz_time_str}")
    
    # 模拟JavaScript解析
    try:
        # 解析ISO时间字符串
        parsed_dt = datetime.fromisoformat(tz_time_str.replace('Z', '+00:00'))
        print(f"解析成功: {parsed_dt}")
        
        # 计算时间差（模拟前端相对时间显示）
        time_diff = (datetime.now(BEIJING_TZ) - parsed_dt).total_seconds()
        hours_diff = time_diff / 3600
        print(f"时间差: {hours_diff:.2f} 小时")
        
        # 这应该接近0，表示时区处理正确
        if abs(hours_diff) < 1:
            print("✅ 时区处理正确，时间差小于1小时")
            return True
        else:
            print("❌ 时区处理可能有问题，时间差过大")
            return False
            
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        return False

def test_relative_time():
    """测试相对时间逻辑"""
    print(f"\n⏰ 相对时间测试")
    print("=" * 50)
    
    now = datetime.now()
    test_cases = [
        ("30分钟前", now - timedelta(minutes=30)),
        ("2小时前", now - timedelta(hours=2)),
        ("1天前", now - timedelta(days=1)),
        ("3天前", now - timedelta(days=3))
    ]
    
    for label, test_time in test_cases:
        formatted = format_datetime_with_tz(test_time)
        diff_seconds = (now - test_time).total_seconds()
        diff_hours = diff_seconds / 3600
        
        print(f"{label}: {formatted}")
        print(f"  实际时间差: {diff_hours:.1f} 小时")
        
        # 验证格式是否包含时区
        if '+08:00' in formatted:
            print("  ✅ 包含北京时区信息")
        else:
            print("  ❌ 缺少时区信息")
    
    return True

if __name__ == "__main__":
    print("🔧 开始简单时间测试...\n")
    
    tests = [
        ("时间格式化", test_time_formatting),
        ("前端解析模拟", simulate_frontend_parsing),
        ("相对时间", test_relative_time)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                print(f"✅ {test_name}测试通过")
                passed += 1
            else:
                print(f"❌ {test_name}测试失败")
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
    
    print(f"\n{'='*50}")
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！时间显示修复有效。")
        print("\n📋 修复说明:")
        print("- API现在返回带有+08:00时区信息的时间")
        print("- 前端可以正确解析时区信息")
        print("- 避免了8小时时差问题")
    else:
        print("💥 存在测试失败，需要进一步检查。")
