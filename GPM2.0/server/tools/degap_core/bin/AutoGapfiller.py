#!/usr/bin/env python3
"""
AutoGapfiller v2.0 - Main Pipeline Script

整合所有步骤的主脚本，自动化执行完整的 gap filling 流程。

流程：
1. Reads Preprocessing (Part1)
2. Gap Detection (Part2)
3. Gap Filling (Part3)
4. Genome Integration (Part4)
5. Visualization (Part5)

作者：DEGAPv2 Team
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import argparse

# 导入各个 Part 的类
try:
    from AutoGapfillerPart1 import ReadsPreprocessor
    from AutoGapfillerPart2 import GapDetector
    from AutoGapfillerPart3 import JobManager, JobExecutor
    from AutoGapfillerPart4 import GenomeIntegrator
    from AutoGapfillerVisualizer import GapFillingVisualizer
except ImportError as e:
    print(f"\n❌ Error: Failed to import required modules: {e}")
    print("Please ensure all AutoGapfillerPart*.py files are in the same directory.")
    sys.exit(1)


class AutoGapfiller:
    """AutoGapfiller 主流程控制器"""
    
    def __init__(self, args):
        """
        初始化主流程控制器
        
        Args:
            args: 命令行参数对象
        """
        self.args = args
        self.output_dir = Path(args.output)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 记录开始时间
        self.start_time = datetime.now()
        
        # 存储各步骤结果
        self.results = {}
        
        # 验证输入文件
        self._validate_inputs()
    
    def _validate_inputs(self):
        """验证输入文件是否存在"""
        print(f"\n{'='*80}")
        print(f"Validating input files...")
        print(f"{'='*80}\n")
        
        # 验证基因组文件
        genome_file = Path(self.args.genome)
        if not genome_file.exists():
            raise FileNotFoundError(f"Genome file not found: {genome_file}")
        print(f"  ✓ Genome file: {genome_file}")
        
        # 验证 HiFi reads（支持多文件）
        if self.args.hifi:
            for hifi in self.args.hifi:
                hifi_file = Path(hifi)
                if not hifi_file.exists():
                    raise FileNotFoundError(f"HiFi reads file not found: {hifi_file}")
            print(f"  ✓ HiFi reads ({len(self.args.hifi)} file(s))")
            for hifi in self.args.hifi:
                print(f"      - {Path(hifi)}")
        
        # 验证 ONT reads（支持多文件）
        if self.args.ont:
            for ont in self.args.ont:
                ont_file = Path(ont)
                if not ont_file.exists():
                    raise FileNotFoundError(f"ONT reads file not found: {ont_file}")
            print(f"  ✓ ONT reads ({len(self.args.ont)} file(s))")
            for ont in self.args.ont:
                print(f"      - {Path(ont)}")
        
        print(f"  ✓ Output directory: {self.output_dir}")
        print(f"\n✅ All input files validated")
    
    def run(self):
        """运行完整流程"""
        print(f"\n{'='*80}")
        print(f"AutoGapfiller v2.0 - Gap Filling Pipeline")
        print(f"{'='*80}")
        print(f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if self.args.setup_only:
            print(f"Mode: Setup Only (will not execute gap filling)")
        print(f"{'='*80}\n")

        try:
            # Step 1: Reads Preprocessing
            self._run_step1()

            # Step 2: Gap Detection
            self._run_step2()

            # Step 3: Gap Filling (setup or full execution)
            if self.args.setup_only:
                self._run_step3_setup_only()
            else:
                self._run_step3()

            # 如果是 setup_only 模式，到此结束
            if self.args.setup_only:
                self._display_setup_only_results()
                return

            # Step 4: Genome Integration
            self._run_step4()

            # Step 5: Visualization
            self._run_step5()

            # 生成总结报告
            self._generate_summary()

            # 显示最终结果
            self._display_final_results()

        except Exception as e:
            print(f"\n{'='*80}")
            print(f"❌ Pipeline failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*80}")
            print(f"\nError: {e}\n")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def _run_step1(self):
        """Step 1: Reads Preprocessing (包含可选的深度过滤)"""
        print(f"\n{'='*80}")
        print(f"[Step 1/5] Reads Preprocessing")
        print(f"{'='*80}")
        
        step_start = datetime.now()
        
        # 传递深度过滤参数到 ReadsPreprocessor
        preprocessor = ReadsPreprocessor(
            self.output_dir,
            filterDepthHifi=self.args.filterDepthHifi,
            filterDepthOnt=self.args.filterDepthOnt
        )
        result = preprocessor.process(self.args.hifi, self.args.ont)
        
        step_end = datetime.now()
        step_duration = step_end - step_start
        
        self.results['step1'] = {
            'name': 'Reads Preprocessing',
            'status': 'completed',
            'start_time': step_start.isoformat(),
            'end_time': step_end.isoformat(),
            'duration': str(step_duration),
            'result': result
        }
        
        print(f"\n✅ Step 1 completed in {step_duration}")
    
    def _run_step2(self):
        """Step 2: Gap Detection"""
        print(f"\n{'='*80}")
        print(f"[Step 2/5] Gap Detection")
        print(f"{'='*80}")
        
        step_start = datetime.now()
        
        detector = GapDetector(self.args.genome, self.output_dir)
        result = detector.detect()
        
        step_end = datetime.now()
        step_duration = step_end - step_start
        
        self.results['step2'] = {
            'name': 'Gap Detection',
            'status': 'completed',
            'start_time': step_start.isoformat(),
            'end_time': step_end.isoformat(),
            'duration': str(step_duration),
            'result': result
        }
        
        print(f"\n✅ Step 2 completed in {step_duration}")
    
    def _run_step3(self):
        """Step 3: Gap Filling"""
        print(f"\n{'='*80}")
        print(f"[Step 3/5] Gap Filling")
        print(f"{'='*80}")

        step_start = datetime.now()

        # 构建 DEGAP 参数
        degap_params = self._build_degap_params()

        # Step 3.1: Setup working directories and job configuration
        print(f"\n[Step 3.1] Setting up working directories...")
        manager = JobManager(self.output_dir, degap_params)
        setup_result = manager.setup_jobs()

        # Step 3.2: Execute gap filling jobs
        print(f"\n[Step 3.2] Executing gap filling jobs...")
        executor = JobExecutor(self.output_dir, workers=self.args.work)
        result = executor.execute_jobs()

        step_end = datetime.now()
        step_duration = step_end - step_start

        self.results['step3'] = {
            'name': 'Gap Filling',
            'status': 'completed',
            'start_time': step_start.isoformat(),
            'end_time': step_end.isoformat(),
            'duration': str(step_duration),
            'setup_result': setup_result,
            'result': result
        }

        print(f"\n✅ Step 3 completed in {step_duration}")

    def _run_step3_setup_only(self):
        """Step 3: Gap Filling (Setup Only - 只创建任务，不执行)"""
        print(f"\n{'='*80}")
        print(f"[Step 3/5] Gap Filling - Setup Only")
        print(f"{'='*80}")

        step_start = datetime.now()

        # 构建 DEGAP 参数
        degap_params = self._build_degap_params()

        # Step 3.1: Setup working directories and job configuration
        print(f"\n[Step 3.1] Setting up working directories...")
        manager = JobManager(self.output_dir, degap_params)
        setup_result = manager.setup_jobs()

        # Step 3.2: 不执行，只显示信息
        print(f"\n[Step 3.2] Skipping job execution (--setup_only mode)")
        print(f"\n📋 Setup completed. Job scripts have been generated.")
        print(f"   To execute gap filling manually, run:")
        print(f"   python DEGAPv2/AutoGapfillerPart3.py \\")
        print(f"       --output {self.output_dir} \\")
        if self.args.hifi:
            print(f"       --hifi {' '.join(self.args.hifi)} \\")
        if self.args.ont:
            print(f"       --ont {' '.join(self.args.ont)} \\")
        print(f"       --work {self.args.work}")

        # 添加可选参数到命令提示
        optional_params = []
        if self.args.thread:
            optional_params.append(f"-t {self.args.thread}")
        if self.args.kmer_filter:
            optional_params.append("--kmer_filter")
        if self.args.MaximumExtensionRound:
            optional_params.append(f"--MaximumExtensionRound {self.args.MaximumExtensionRound}")
        if self.args.MaximumExtensionLength:
            optional_params.append(f"--MaximumExtensionLength {self.args.MaximumExtensionLength}")

        if optional_params:
            print(f"       {' '.join(optional_params)}")

        step_end = datetime.now()
        step_duration = step_end - step_start

        self.results['step3'] = {
            'name': 'Gap Filling (Setup Only)',
            'status': 'setup_completed',
            'start_time': step_start.isoformat(),
            'end_time': step_end.isoformat(),
            'duration': str(step_duration),
            'setup_result': setup_result,
            'execution_skipped': True
        }

        print(f"\n✅ Step 3 setup completed in {step_duration}")

    def _run_step4(self):
        """Step 4: Genome Integration"""
        print(f"\n{'='*80}")
        print(f"[Step 4/5] Genome Integration")
        print(f"{'='*80}")
        
        step_start = datetime.now()
        
        integrator = GenomeIntegrator(self.output_dir)
        result = integrator.integrate()
        
        step_end = datetime.now()
        step_duration = step_end - step_start
        
        self.results['step4'] = {
            'name': 'Genome Integration',
            'status': 'completed',
            'start_time': step_start.isoformat(),
            'end_time': step_end.isoformat(),
            'duration': str(step_duration),
            'result': result
        }
        
        print(f"\n✅ Step 4 completed in {step_duration}")
    
    def _run_step5(self):
        """Step 5: Visualization"""
        print(f"\n{'='*80}")
        print(f"[Step 5/5] Visualization")
        print(f"{'='*80}")
        
        step_start = datetime.now()
        
        visualizer = GapFillingVisualizer(self.output_dir)
        result = visualizer.generate_report()
        
        step_end = datetime.now()
        step_duration = step_end - step_start
        
        self.results['step5'] = {
            'name': 'Visualization',
            'status': 'completed',
            'start_time': step_start.isoformat(),
            'end_time': step_end.isoformat(),
            'duration': str(step_duration),
            'result': result
        }
        
        print(f"\n✅ Step 5 completed in {step_duration}")
    
    def _build_degap_params(self):
        """
        构建 DEGAP 参数字典
        NOTE: 不包含 filterDepthHifi/Ont，因为深度过滤已在 Step 1 统一完成
        """
        params = {
            'hifi': self.args.hifi,
            'ont': self.args.ont,
        }
        
        # 添加可选参数（只添加用户指定的）
        if self.args.thread is not None:
            params['thread'] = str(self.args.thread)
        if self.args.remove is not None:
            params['remove'] = self.args.remove
        if self.args.edge is not None:
            params['edge'] = self.args.edge
        # filterDepthHifi/Ont 已在 Step 1 完成，不再传递给 DEGAP.py
        # if self.args.filterDepthHifi is not None:
        #     params['filterDepthHifi'] = self.args.filterDepthHifi
        # if self.args.filterDepthOnt is not None:
        #     params['filterDepthOnt'] = self.args.filterDepthOnt
        if self.args.MaximumExtensionLength is not None:
            params['MaximumExtensionLength'] = self.args.MaximumExtensionLength
        if self.args.MaximumExtensionRound is not None:
            params['MaximumExtensionRound'] = self.args.MaximumExtensionRound
        if self.args.kmer_filter:
            params['kmer_filter'] = True
        if self.args.kmer_size is not None:
            params['kmer_size'] = self.args.kmer_size
        if self.args.kmer_num is not None:
            params['kmer_num'] = self.args.kmer_num
        # Note: -j parameter removed, parallel control unified under -t parameter

        return params
    
    def _generate_summary(self):
        """生成总结报告"""
        end_time = datetime.now()
        total_duration = end_time - self.start_time
        
        summary = {
            'version': '2.0',
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_duration': str(total_duration),
            'parameters': {
                'genome': self.args.genome,
                'hifi': self.args.hifi,
                'ont': self.args.ont,
                'output': str(self.output_dir),
                'workers': self.args.work,
                'thread': self.args.thread,
                'kmer_filter': self.args.kmer_filter,
                'kmer_size': self.args.kmer_size,
                'kmer_num': self.args.kmer_num,
                'MaximumExtensionLength': self.args.MaximumExtensionLength,
                'MaximumExtensionRound': self.args.MaximumExtensionRound,
                'filterDepthHifi': self.args.filterDepthHifi,
                'filterDepthOnt': self.args.filterDepthOnt,
                'edge': self.args.edge,
                'remove': self.args.remove
                # Note: -j parameter removed, parallel control unified under -t parameter
            },
            'steps': self.results
        }
        
        # 保存到文件
        summary_file = self.output_dir / 'autogapfiller_summary.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\n📄 Summary saved to: {summary_file}")

    def _display_setup_only_results(self):
        """显示 setup_only 模式的结果"""
        end_time = datetime.now()
        total_duration = end_time - self.start_time

        print(f"\n{'='*80}")
        print(f"✅ Setup Completed Successfully!")
        print(f"{'='*80}")
        print(f"Start time:  {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End time:    {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration:    {total_duration}")
        print(f"{'='*80}\n")

        # 显示已完成的步骤
        print("✅ Completed Steps:")
        print(f"  1. Reads Preprocessing")
        print(f"  2. Gap Detection")
        print(f"  3. Gap Filling Setup (job scripts created)")

        # 显示关键输出目录
        print(f"\n📁 Key Output Directories:")
        print(f"  • Preprocessed reads: {self.output_dir}/01.reads_preprocessor/")
        print(f"  • Gap detection:      {self.output_dir}/02.gap_detection/")
        print(f"  • Job scripts:        {self.output_dir}/03.gap_filling/")

        # 显示 gap 统计信息
        if 'step2' in self.results and 'result' in self.results['step2']:
            gap_result = self.results['step2']['result']
            if 'total_gaps' in gap_result:
                print(f"\n📊 Gap Detection Statistics:")
                print(f"  • Total gaps found:   {gap_result['total_gaps']}")
                if 'gaps_by_scaffold' in gap_result:
                    print(f"  • Scaffolds with gaps: {len(gap_result['gaps_by_scaffold'])}")

        # 显示 job 设置信息
        if 'step3' in self.results and 'setup_result' in self.results['step3']:
            setup_result = self.results['step3']['setup_result']
            if 'total_jobs' in setup_result:
                print(f"\n📋 Job Setup Statistics:")
                print(f"  • Total jobs created: {setup_result['total_jobs']}")
                print(f"  • Job directories:    {self.output_dir}/03.gap_filling/*/")

        # 显示下一步操作
        print(f"\n{'='*80}")
        print(f"📌 Next Steps:")
        print(f"{'='*80}")
        print(f"\n1. Review the generated job scripts in:")
        print(f"   {self.output_dir}/03.gap_filling/")
        print(f"\n2. To execute gap filling, run:")
        print(f"   python DEGAPv2/AutoGapfillerPart3.py \\")
        print(f"       --output {self.output_dir} \\")
        if self.args.hifi:
            print(f"       --hifi {' '.join(self.args.hifi)} \\")
        if self.args.ont:
            print(f"       --ont {' '.join(self.args.ont)} \\")
        print(f"       --work {self.args.work}")

        # 添加可选参数
        optional_params = []
        if self.args.thread:
            optional_params.append(f"-t {self.args.thread}")
        if self.args.kmer_filter:
            optional_params.append("--kmer_filter")
        if self.args.MaximumExtensionRound:
            optional_params.append(f"--MaximumExtensionRound {self.args.MaximumExtensionRound}")
        if self.args.MaximumExtensionLength:
            optional_params.append(f"--MaximumExtensionLength {self.args.MaximumExtensionLength}")

        if optional_params:
            print(f"       {' '.join(optional_params)}")

        print(f"\n3. Or re-run AutoGapfiller without --setup_only to execute all steps")
        print(f"{'='*80}\n")

        # 保存 setup 总结
        summary = {
            'version': '2.0',
            'mode': 'setup_only',
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_duration': str(total_duration),
            'parameters': {
                'genome': self.args.genome,
                'hifi': self.args.hifi,
                'ont': self.args.ont,
                'output': str(self.output_dir),
                'workers': self.args.work,
                'thread': self.args.thread,
                'kmer_filter': self.args.kmer_filter,
                'setup_only': True
            },
            'results': self.results
        }

        summary_file = self.output_dir / 'autogapfiller_setup_summary.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"📄 Setup summary saved to: {summary_file}\n")

    def _display_final_results(self):
        """显示最终结果"""
        end_time = datetime.now()
        total_duration = end_time - self.start_time
        
        print(f"\n{'='*80}")
        print(f"✅ Pipeline Completed Successfully!")
        print(f"{'='*80}")
        print(f"Start time:  {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End time:    {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration:    {total_duration}")
        print(f"{'='*80}\n")
        
        # 显示关键输出文件
        print("📁 Key Output Files:")
        print(f"  • Filled genome:     {self.output_dir}/04.genome_integration/genome.filled.fasta")
        print(f"  • Visualization:     {self.output_dir}/05.visualization/gap_filling_report.html")
        print(f"  • Gap statistics:    {self.output_dir}/03.gap_filling/gap_filling_results.json")
        print(f"  • Summary report:    {self.output_dir}/autogapfiller_summary.json")
        
        # 显示统计信息（如果有）
        if 'step3' in self.results and 'result' in self.results['step3']:
            step3_result = self.results['step3']['result']
            if 'summary' in step3_result:
                summary = step3_result['summary']
                print(f"\n📊 Gap Filling Statistics:")
                print(f"  • Total gaps:        {summary.get('total_jobs', 'N/A')}")
                print(f"  • Completed:         {summary.get('completed', 'N/A')}")
                print(f"  • Failed:            {summary.get('failed', 'N/A')}")
        
        print(f"\n{'='*80}\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='AutoGapfiller v2.0 - Automated Gap Filling Pipeline',
        epilog='''
Examples:
  # Minimum (HiFi-only)
  %(prog)s -g genome.fasta --hifi hifi.fq.gz -o output

  # Recommended (HiFi + ONT with k-mer filter)
  %(prog)s -g genome.fasta --hifi hifi.fq.gz --ont ont.fq.gz -o output -w 10 --kmer_filter

  # Advanced (with custom parameters)
  %(prog)s -g genome.fasta --hifi hifi.fq.gz --ont ont.fq.gz -o output \\
      -w 20 -t 30 --kmer_filter -ks 51 -kn 30 \\
      --MaximumExtensionLength 500000 --filterDepthHifi 3.0

  # Setup only (prepare jobs without execution)
  %(prog)s -g genome.fasta --hifi hifi.fq.gz -o output --setup_only

For more information, visit: https://github.com/your-repo/DEGAPv2
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # 必需参数
    required = parser.add_argument_group('required arguments')
    required.add_argument('--genome', '-g', required=True, 
                         help='Genome FASTA file')
    required.add_argument('--output', '-o', required=True, 
                         help='Output directory')
    
    # Reads 文件（至少一个）
    reads = parser.add_argument_group('reads files (at least one required)')
    reads.add_argument('--hifi', nargs='+',
                      help='HiFi reads file(s) (FASTA/FASTQ, .gz supported; multiple files supported)')
    reads.add_argument('--ont', nargs='+',
                      help='ONT reads file(s) (FASTA/FASTQ, .gz supported; multiple files supported)')
    
    # 常用参数
    common = parser.add_argument_group('common parameters')
    common.add_argument('--work', '-w', type=int, default=1,
                       help='Number of parallel workers (default: 1)')
    common.add_argument('--kmer_filter', action='store_true',
                       help='Enable k-mer filtering')
    common.add_argument('--setup_only', action='store_true',
                       help='Only setup job directories and scripts without executing gap filling. '
                            'Useful for reviewing generated commands before execution')
    
    # 高级参数
    advanced = parser.add_argument_group('advanced parameters')
    advanced.add_argument('--thread', '-t', type=int, default=20,
                         help='Number of threads for DEGAP (default: 20)')
    advanced.add_argument('--kmer_size', '-ks', type=int, default=41,
                         help='K-mer size (default: 41)')
    advanced.add_argument('--kmer_num', '-kn', type=int, default=20,
                         help='Number of k-mers (default: 20)')
    advanced.add_argument('--MaximumExtensionLength', type=int,
                         help='Maximum cumulative extension length in bp (default: None, no limit). '
                              'Extension stops when total extended length exceeds this value')
    advanced.add_argument('--MaximumExtensionRound', type=int,
                         help='Maximum number of extension rounds (default: None, no limit). '
                              'Extension stops when round number exceeds this value. '
                              'Minimum recommended value is 5')
    advanced.add_argument('--filterDepthHifi', type=float,
                         help='Filter HiFi reads by mapped depth. '
                              'Example: 0.3 means keep reads with depth >= 0.3*avgdepth and depth <= (2-0.3)*avgdepth')
    advanced.add_argument('--filterDepthOnt', type=float,
                         help='Filter ONT reads by mapped depth. '
                              'Example: 0.2 means keep reads with depth >= 0.2*avgdepth and depth <= (2-0.2)*avgdepth')
    advanced.add_argument('--edge', type=int, default=500,
                         help='Edge length for misassembly detection (default: 500)')
    advanced.add_argument('--remove', type=int, choices=[1, 2, 3], default=2,
                         help='File cleanup level: 1=keep all, 2=remove some, 3=remove most (default: 2)')
    
    args = parser.parse_args()
    
    # 验证至少指定了 HiFi 或 ONT
    if not args.hifi and not args.ont:
        parser.error("At least one of --hifi or --ont must be specified")
    
    # 运行流程
    pipeline = AutoGapfiller(args)
    pipeline.run()


if __name__ == '__main__':
    main()

