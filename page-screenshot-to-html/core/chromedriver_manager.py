"""
ChromeDriver管理模块
负责ChromeDriver的检查、下载、版本匹配
"""

import os
import platform
import subprocess
import urllib.request
import zipfile
import shutil
from pathlib import Path
from typing import Optional, Tuple


class ChromeDriverManager:
    """ChromeDriver管理器"""
    
    def __init__(self, chromedriver_dir: Optional[str] = None):
        if chromedriver_dir is None:
            self.chromedriver_dir = Path(__file__).parent.parent / 'scripts'
        else:
            self.chromedriver_dir = Path(chromedriver_dir)
        
        self.chromedriver_path = self.chromedriver_dir / 'chromedriver'
        
    def check_and_setup(self) -> Optional[str]:
        """检查并设置ChromeDriver，包括环境检测和自动修复"""
        print("\n" + "="*60)
        print("ChromeDriver 环境检测")
        print("="*60)
        
        # 1. 检查ChromeDriver是否存在
        if not self.chromedriver_path.exists():
            print("❌ ChromeDriver未找到")
            print(f"   期望路径: {self.chromedriver_path}")
            print("\n正在尝试自动下载ChromeDriver...")
            return self._download()
        
        print(f"✅ ChromeDriver存在: {self.chromedriver_path}")
        
        # 2. 检查文件权限
        if not os.access(self.chromedriver_path, os.X_OK):
            print("⚠️ ChromeDriver没有执行权限，正在修复...")
            try:
                os.chmod(self.chromedriver_path, 0o755)
                print("✅ 权限修复完成")
            except Exception as e:
                print(f"❌ 权限修复失败: {e}")
                return None
        
        # 3. 检查架构是否匹配
        try:
            result = subprocess.run(['file', str(self.chromedriver_path)], 
                                  capture_output=True, text=True)
            file_info = result.stdout
            print(f"   文件信息: {file_info.strip()}")
            
            # 检查当前系统架构
            machine = platform.machine()
            print(f"   系统架构: {machine}")
            
            # 检查是否匹配
            if 'x86-64' in file_info or 'x86_64' in file_info:
                if machine in ['x86_64', 'AMD64']:
                    print("✅ 架构匹配: x86_64")
                else:
                    print("⚠️ 架构不匹配! ChromeDriver是x86_64，但系统不是")
                    print("正在尝试重新下载匹配版本的ChromeDriver...")
                    return self._download()
            elif 'aarch64' in file_info or 'arm64' in file_info:
                if machine in ['aarch64', 'arm64']:
                    print("✅ 架构匹配: ARM64")
                else:
                    print("⚠️ 架构不匹配! ChromeDriver是ARM64，但系统不是")
                    print("正在尝试重新下载匹配版本的ChromeDriver...")
                    return self._download()
            
        except Exception as e:
            print(f"⚠️ 架构检查失败: {e}")
            print("继续使用现有的ChromeDriver...")
        
        # 4. 检查ChromeDriver版本是否与Chrome浏览器版本匹配
        try:
            print("\n检查ChromeDriver版本兼容性...")
            
            # 获取Chrome浏览器版本
            chrome_version, chrome_major = self._get_chrome_version()
            if chrome_version and chrome_major:
                print(f"   Chrome浏览器版本: {chrome_version}")
                
                # 获取ChromeDriver版本
                result = subprocess.run([str(self.chromedriver_path), '--version'], 
                                      capture_output=True, text=True)
                chromedriver_version_line = result.stdout.strip()
                # 格式通常是 "ChromeDriver 120.0.6099.109"
                if 'ChromeDriver' in chromedriver_version_line:
                    chromedriver_version = chromedriver_version_line.split()[1]
                    chromedriver_major = chromedriver_version.split('.')[0]
                    print(f"   ChromeDriver版本: {chromedriver_version}")
                    
                    # 比较主版本号
                    if chrome_major == chromedriver_major:
                        print(f"✅ 版本匹配: {chrome_major}")
                    else:
                        print(f"⚠️ 版本不匹配!")
                        print(f"   Chrome浏览器: {chrome_major}")
                        print(f"   ChromeDriver: {chromedriver_major}")
                        print("\n正在删除旧版本ChromeDriver并重新下载...")
                        try:
                            os.remove(self.chromedriver_path)
                            print("✅ 旧版本已删除")
                            return self._download()
                        except Exception as e:
                            print(f"❌ 删除失败: {e}")
                            return None
            else:
                print("⚠️ 无法检测Chrome版本，跳过版本检查")
                
        except Exception as e:
            print(f"⚠️ 版本检查失败: {e}")
            print("继续使用现有的ChromeDriver...")
        
        print("="*60 + "\n")
        return str(self.chromedriver_path)
    
    def _get_chrome_version(self) -> Tuple[Optional[str], Optional[str]]:
        """获取当前安装的Chrome浏览器版本"""
        try:
            result = subprocess.run(['google-chrome', '--version'], 
                                  capture_output=True, text=True)
            version_line = result.stdout.strip()
            # 解析版本号，格式通常是 "Google Chrome 146.0.7680.177"
            if 'Google Chrome' in version_line:
                version = version_line.split()[-1]
                # 获取主版本号（如 146）
                major_version = version.split('.')[0]
                return version, major_version
            return None, None
        except Exception as e:
            print(f"⚠️ 获取Chrome版本失败: {e}")
            return None, None
    
    def _download(self) -> Optional[str]:
        """下载匹配当前系统的ChromeDriver"""
        # 获取Chrome版本
        chrome_version, chrome_major = self._get_chrome_version()
        
        print(f"\n{'='*60}")
        print("ChromeDriver 自动下载")
        print("="*60)
        
        if chrome_version:
            print(f"检测到Chrome版本: {chrome_version}")
            print(f"主版本号: {chrome_major}")
        else:
            print("⚠️ 无法检测Chrome版本，将使用默认版本 120")
            chrome_major = "120"
        
        # 确定系统架构
        machine = platform.machine()
        system = platform.system().lower()
        
        print(f"\n系统信息: {system} {machine}")
        
        # 尝试下载匹配Chrome版本的ChromeDriver
        base_url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing"
        
        # 尝试下载匹配Chrome版本的driver
        driver_versions_to_try = []
        
        if chrome_major and chrome_major.isdigit():
            # 构建可能的版本号
            major = int(chrome_major)
            driver_versions_to_try.append(f"{major}.0.7680.0")
            driver_versions_to_try.append(f"{major}.0.0.0")
        
        # 如果特定版本失败，使用已知稳定的版本
        driver_versions_to_try.extend([
            "146.0.7680.0",  # Chrome 146
            "145.0.7668.0",  # Chrome 145
            "144.0.7655.0",  # Chrome 144
            "120.0.6099.109",  # 默认版本
        ])
        
        # 确定平台路径
        if system == 'linux':
            if machine in ['x86_64', 'AMD64']:
                platform_path = "linux64"
                chromedriver_name = "chromedriver-linux64"
            else:
                print(f"❌ 不支持的架构: {machine}")
                return None
        elif system == 'darwin':  # macOS
            if machine in ['x86_64', 'AMD64']:
                platform_path = "mac-x64"
                chromedriver_name = "chromedriver-mac-x64"
            else:
                platform_path = "mac-arm64"
                chromedriver_name = "chromedriver-mac-arm64"
            print("❌ macOS暂不支持自动下载，请手动安装ChromeDriver")
            return None
        else:
            print(f"❌ 不支持的操作系统: {system}")
            return None
        
        # 尝试下载每个版本
        for version in driver_versions_to_try:
            url = f"{base_url}/{version}/{platform_path}/{chromedriver_name}.zip"
            
            print(f"\n尝试下载版本 {version}...")
            print(f"URL: {url}")
            
            try:
                zip_file = self.chromedriver_dir / f"{chromedriver_name}.zip"
                
                # 下载
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    with open(zip_file, 'wb') as f:
                        f.write(response.read())
                
                print(f"✅ 下载完成")
                
                # 解压
                print("正在解压...")
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(self.chromedriver_dir)
                print("✅ 解压完成")
                
                # 移动chromedriver到正确位置
                extracted_driver = self.chromedriver_dir / chromedriver_name / 'chromedriver'
                if extracted_driver.exists():
                    if self.chromedriver_path.exists():
                        os.remove(self.chromedriver_path)
                    os.rename(extracted_driver, self.chromedriver_path)
                    os.chmod(self.chromedriver_path, 0o755)
                    print(f"✅ ChromeDriver {version} 已安装")
                    
                    # 清理临时文件
                    if zip_file.exists():
                        os.remove(zip_file)
                    extract_dir_path = self.chromedriver_dir / chromedriver_name
                    if extract_dir_path.exists():
                        shutil.rmtree(extract_dir_path)
                    
                    return str(self.chromedriver_path)
                else:
                    print(f"❌ 解压后未找到ChromeDriver")
                    
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    print(f"⚠️ 版本 {version} 不存在，尝试下一个版本...")
                else:
                    print(f"❌ HTTP错误 {e.code}: {e.reason}")
            except Exception as e:
                print(f"❌ 下载失败: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n❌ 所有版本都下载失败")
        return None


# 便捷函数
def get_chromedriver_path() -> Optional[str]:
    """获取ChromeDriver路径，如果不存在则尝试下载"""
    manager = ChromeDriverManager()
    return manager.check_and_setup()
