import re
import Bio
import os
import sys
import re
import getopt
import subprocess
import pysam
import time
from pysam import AlignmentFile
import Bio
from Bio import SeqIO
from collections import defaultdict

class FindExtensionReads(object):
	def __init__(self,roundInput,lastRoundUsedReads,usedReads,kmer_size=41,kmer_num=300,out=None):
		# Import required modules
		import os
		import traceback

		self.roundInput=roundInput
		self.lastRoundUsedReads=lastRoundUsedReads
		self.usedReads=usedReads
		self.note=''
		self.kmer_size=kmer_size
		self.kmer_num=kmer_num
		self.out=out
		# 根据数据类型设置文件命名
		if hasattr(self.roundInput.elongation.base, 'data_type'):
			if self.roundInput.elongation.base.data_type == 'mixed':
				# 混合模式：使用规范命名
				self.extensionReads = self.roundInput.elongation.roundDir+"/hifi.extensionReads."+self.roundInput.elongation.base.tag+".fa"
				self.log = self.roundInput.elongation.roundDir+"/hifi.extensionReads.log"
				self.ont_extensionReads = self.roundInput.elongation.roundDir+"/ont.extensionReads."+self.roundInput.elongation.base.tag+".fa"
				self.ont_log = self.roundInput.elongation.roundDir+"/ont.extensionReads.log"
			elif self.roundInput.elongation.base.data_type == 'hifi':
				# HiFi单一模式
				self.extensionReads = self.roundInput.elongation.roundDir+"/hifi.extensionReads."+self.roundInput.elongation.base.tag+".fa"
				self.log = self.roundInput.elongation.roundDir+"/hifi.extensionReads.log"
			elif self.roundInput.elongation.base.data_type == 'ont':
				# ONT单一模式
				self.extensionReads = self.roundInput.elongation.roundDir+"/ont.extensionReads."+self.roundInput.elongation.base.tag+".fa"
				self.log = self.roundInput.elongation.roundDir+"/ont.extensionReads.log"
			else:
				# 未知数据类型，使用原有命名作为fallback
				print(f"Warning: Unknown data_type '{self.roundInput.elongation.base.data_type}', using default naming")
				self.extensionReads = self.roundInput.elongation.roundDir+"/extensionReads."+self.roundInput.elongation.base.tag+".fa"
				self.log = self.roundInput.elongation.roundDir+"/extensionReads.log"
		else:
			# 向后兼容：使用原有命名
			self.extensionReads = self.roundInput.elongation.roundDir+"/extensionReads."+self.roundInput.elongation.base.tag+".fa"
			self.log = self.roundInput.elongation.roundDir+"/extensionReads.log"

		# Ensure output directory exists
		if not os.path.exists(self.roundInput.elongation.roundDir):
			try:
				os.makedirs(self.roundInput.elongation.roundDir)
				print(f"Created output directory: {self.roundInput.elongation.roundDir}")
			except Exception as e:
				print(f"Failed to create output directory: {e}")

		if os.path.exists(self.extensionReads)==True and os.path.getsize(self.extensionReads)!=0:
			self.readlog()
		else:
			logfilet=open(self.log,'w')
			try:
				# 直接执行minimap2（已移除kmer过滤回退机制）
				minimap2_result = self.minimap2()
				if minimap2_result is None:
					# minimap2返回None，可能是因为k-mer粗筛没有结果或没有合适的reads
					print("minimap2未找到合适的reads（k-mer粗筛无结果或无匹配reads）")
					self.potentialExtensionReadsAln = None
					self.minimap2Command = None
					self.minimap2Output = None
					self.extensionReadsNum = 0
					self.note = 'kmerFilterNoReads'  # 设置note以终止后续处理
					logLine='note\tkmerFilterNoReads\nextensionReadsNum\t0\n'
					logfilet.writelines(logLine)
				else:
					self.potentialExtensionReadsAln,self.minimap2Command,self.minimap2Output = minimap2_result
					logLine='potentialExtensionReadsAln\t'+self.potentialExtensionReadsAln+"\nminimap2Command\t"+self.minimap2Command+"\nminimap2Output\t"+self.minimap2Output+"\n"
					logfilet.writelines(logLine)

				# 只有在minimap2成功的情况下才继续执行
				if self.potentialExtensionReadsAln is not None:
					self.minimumExtensionReads()

					# Check if minimumExtensionReads successfully set necessary attributes
					if hasattr(self, 'minimumThresholdReadsAln'):
						logLine='minimumThresholdReadsAln\t'+self.minimumThresholdReadsAln+"\n"
						logfilet.writelines(logLine)

					if hasattr(self, 'minimumThresholdReadsID'):
						logLine='minimumThresholdReadsID\t'+';'.join(self.minimumThresholdReadsID)+"\n"
						logfilet.writelines(logLine)

					if hasattr(self, 'minimumThresholdExtensionReadsAln'):
						logLine='minimumThresholdExtensionReadsAln\t'+self.minimumThresholdExtensionReadsAln+"\n"
						logfilet.writelines(logLine)

					if hasattr(self, 'minimumThresholdExtensionReads'):
						logLine='minimumThresholdExtensionReads\t'+self.minimumThresholdExtensionReads+"\n"
						logfilet.writelines(logLine)

					if hasattr(self, 'minimumThresholdExtensionReadsID'):
						logLine='minimumThresholdExtensionReadsID\t'+';'.join(self.minimumThresholdExtensionReadsID)+"\n"
						logfilet.writelines(logLine)
				else:
					# 当k-mer过滤失败或minimap2失败时，设置默认值
					print("设置默认的extension reads属性")
					self.minimumThresholdReadsAln = None
					self.minimumThresholdReadsID = []
					self.minimumThresholdExtensionReadsAln = None
					self.minimumThresholdExtensionReads = None
					self.minimumThresholdExtensionReadsID = []
			except Exception as e:
				import traceback
				print(f"Error during initialization: {e}")
				traceback.print_exc()
				self.note = 'initializationError'
				logLine='note\t'+self.note+"\n"
				logfilet.writelines(logLine)
				logfilet.close()
				return

			if self.note=='':
				# Initialize extension-related attributes before loop (matching v1 behavior)
				self.selectMappingQuality = 20
				self.selectAlignmentLength = 3000
				self.selectNMAlignmentLengthratio = 0.1

				self.selectReadsNum = 0
				self.extensionReadsNum = 0
				self.readsExtensionLength = 1000
				self.extensionReadsEdge = 10

				# Get the maximum edge value from command line (default: 500)
				max_edge = self.roundInput.elongation.base.edge

				# 根据 data_type 动态选择文件名前缀和 file_prefix 参数
				data_type = getattr(self.roundInput.elongation.base, 'data_type', 'hifi')
				if data_type == 'ont':
					file_prefix = 'ont'
				else:
					# HiFi-only 或 Mixed 模式都使用 hifi 前缀
					file_prefix = 'hifi'

				# ============================================================
				# 使用两层二分搜索优化替代原来的线性 while 循环
				# 原来最坏情况需要 1950 次尝试，现在最多 ~12 次
				# ============================================================
				try:
					# 设置输出文件路径
					self.selectPotentialExtensionReadsAln = self.roundInput.elongation.roundDir + f"/{file_prefix}.selectPotentialExtensionReads." + self.roundInput.elongation.base.tag + ".bam"
					self.extensionReadsAln = self.roundInput.elongation.roundDir + f"/{file_prefix}.extensionReads." + self.roundInput.elongation.base.tag + ".bam"
					
					# 执行两层二分搜索
					success, final_mq, final_el, final_al, final_edge, ext_reads_id = \
						self._binary_search_extension_reads(
							self.minimumThresholdExtensionReadsAln,
							self.selectPotentialExtensionReadsAln,
							self.extensionReadsAln,
							self.extensionReads,
							file_prefix,
							max_edge
						)
					
					# 更新结果
					self.selectMappingQuality = final_mq
					self.readsExtensionLength = final_el
					self.selectAlignmentLength = final_al
					self.extensionReadsEdge = final_edge
					self.extensionReadsID = ext_reads_id if ext_reads_id else []
					self.extensionReadsNum = len(self.extensionReadsID)
					
					if not success:
						self.note = 'noExtensionReadsFoundAfterParameterRelaxation'
						print(f"Info: No extension reads found even after binary search relaxation. This is normal for some gaps.")
					
				except Exception as e:
					import traceback
					print(f"Error in binary search extension reads: {e}")
					traceback.print_exc()
					self.note = 'extensionFinderError'
			# After relaxation attempts, if still no reads and minimum threshold never produced candidates, mark note
			if self.extensionReadsNum <= 0 and self.note == '' and not getattr(self, '_minimum_threshold_extension_found', False):
				self.note = 'noExtensionReadsFoundAtMinimumThreshold'
			
			# Ensure all attributes exist before writing to log
			if not hasattr(self, 'selectPotentialExtensionReadsAln'):
				self.selectPotentialExtensionReadsAln = None
			if not hasattr(self, 'selectPotentialExtensionReadsID'):
				self.selectPotentialExtensionReadsID = []
			if not hasattr(self, 'selectReadsNum'):
				self.selectReadsNum = 0
			if not hasattr(self, 'extensionReadsAln'):
				self.extensionReadsAln = None
			if not hasattr(self, 'extensionReadsID'):
				self.extensionReadsID = []
			
			logLine='selectPotentialExtensionReadsAln\t'+(self.selectPotentialExtensionReadsAln if self.selectPotentialExtensionReadsAln else 'None')+"\n"
			logLine+='selectPotentialExtensionReadsID\t'+(';'.join(self.selectPotentialExtensionReadsID) if self.selectPotentialExtensionReadsID else 'None')+"\n"
			logLine+='selectReadsNum\t'+str(self.selectReadsNum)+"\n"
			logLine+='extensionReadsAln\t'+(self.extensionReadsAln if self.extensionReadsAln else 'None')+"\n"
			logLine+='extensionReads\t'+(self.extensionReads if self.extensionReads else 'None')+"\n"
			logLine+='extensionReadsID\t'+(';'.join(self.extensionReadsID) if self.extensionReadsID else 'None')+"\n"
			logLine+='extensionReadsNum\t'+str(self.extensionReadsNum)+"\n"
			logfilet.writelines(logLine)
			
			logLine='selectMappingQuality\t'+str(self.selectMappingQuality)+"\n"
			logLine+='selectAlignmentLength\t'+str(self.selectAlignmentLength)+"\n"
			logLine+='selectNMAlignmentLengthratio\t'+str(self.selectNMAlignmentLengthratio)+"\n"
			logLine+='readsExtensionLength\t'+str(self.readsExtensionLength)+"\n"
			logLine+='extensionReadsEdge\t'+str(self.extensionReadsEdge)+"\n"
			logLine+='note\t'+str(self.note)+"\n"
			logfilet.writelines(logLine)

			# Process ONT extension reads for mixed mode
			# Only execute ONT flow if HiFi failed to find extension reads
			if hasattr(self, 'ont_extensionReads') and self.roundInput.elongation.base.data_type == 'mixed':
				if hasattr(self, 'extensionReadsNum') and self.extensionReadsNum > 0:
					# HiFi found extension reads, skip ONT processing
					print(f"Mixed mode: HiFi found {self.extensionReadsNum} extension reads, skipping ONT processing")
					self.ont_extensionReadsNum = 0
					self.mixed_mode_status = 'hifi_only'
				else:
					# HiFi failed, execute ONT flow
					print("Mixed mode: HiFi found no extension reads, executing ONT flow...")
					self.processONTExtensionReads()
					# 检查混合模式结果并实现容错机制
					self.checkMixedModeResults()

				# Add ONT information to log after processing
				ont_logLine = f"ont_extensionReads\t{getattr(self, 'ont_extensionReads', 'None')}\n"
				ont_logLine += f"ont_extensionReadsNum\t{getattr(self, 'ont_extensionReadsNum', 0)}\n"
				ont_logLine += f"ont_log\t{getattr(self, 'ont_log', 'None')}\n"
				logfilet.writelines(ont_logLine)
				print("ONT extension reads information added to log")

				# 记录混合模式状态
				if hasattr(self, 'mixed_mode_status'):
					mixed_status_line = f"mixed_mode_status\t{self.mixed_mode_status}\n"
					logfilet.writelines(mixed_status_line)

			logfilet.close()

	def processONTExtensionReads(self):
		"""Process ONT extension reads for mixed mode with minimap2-samFilter-extensionFinder pipeline"""
		import os
		import shutil
		
		print("Processing ONT extension reads for mixed mode...")

		# Check if ONT reads are available
		if not hasattr(self.roundInput.elongation.base, 'ont_reads') or not self.roundInput.elongation.base.ont_reads:
			print("No ONT reads available for mixed mode processing")
			return

		# Check if ONT extension reads already exist
		if os.path.exists(self.ont_extensionReads) and os.path.getsize(self.ont_extensionReads) > 0:
			print(f"ONT extension reads already exist: {self.ont_extensionReads}")
			# Count existing ONT extension reads
			self.ont_extensionReadsNum = 0
			for record in SeqIO.parse(self.ont_extensionReads, 'fasta'):
				self.ont_extensionReadsNum += 1
			print(f"Found {self.ont_extensionReadsNum} existing ONT extension reads")
			return

		# 检查 k-mer 过滤是否启用
		kmer_filter_enabled = getattr(self.roundInput.elongation.base, 'kmer_filter', False)

		if kmer_filter_enabled:
			# K-mer 过滤启用：尝试使用 k-mer 过滤后的 ONT reads
			print("K-mer filtering is ENABLED for ONT reads")
			ont_kmer_reads_file_tag = self.roundInput.elongation.roundDir + f"/ont.kmer.Reads.{self.roundInput.elongation.base.tag}.fa"
			ont_kmer_reads_file_flag = self.roundInput.elongation.roundDir + f"/ont.kmer.Reads.{self.roundInput.elongation.base.flag}.fa"
			ont_reads_to_use = None

			if os.path.exists(ont_kmer_reads_file_tag) and os.path.getsize(ont_kmer_reads_file_tag) > 0:
				ont_reads_to_use = ont_kmer_reads_file_tag
				print(f"Using ONT k-mer filtered reads (tag): {ont_reads_to_use}")
			elif os.path.exists(ont_kmer_reads_file_flag) and os.path.getsize(ont_kmer_reads_file_flag) > 0:
				ont_reads_to_use = ont_kmer_reads_file_flag
				print(f"Using ONT k-mer filtered reads (flag): {ont_reads_to_use}")
			else:
				# K-mer 粗筛没有结果，直接结束 ONT 处理，不回退到全部 reads
				print(f"ONT k-mer filtered reads not found or empty, ending ONT extension")
				print(f"  Checked: {ont_kmer_reads_file_tag}")
				print(f"  Checked: {ont_kmer_reads_file_flag}")
				self.ont_extensionReadsNum = 0
				return
		else:
			# K-mer 过滤未启用：使用 _get_reads_path 获取正确的 ONT reads 路径
			print("K-mer filtering is DISABLED, using processed/original ONT reads")
			ont_reads_to_use = self._get_reads_path('ont')

		# 检查 ONT reads 文件是否存在
		if not ont_reads_to_use or not os.path.exists(ont_reads_to_use):
			print(f"Error: ONT reads file not found: {ont_reads_to_use}")
			self.ont_extensionReadsNum = 0
			return

		print(f"Using ONT reads file: {ont_reads_to_use}")

		try:
			# Stage 1: ONT minimap2 alignment
			print("Stage 1: ONT minimap2 alignment...")
			ont_potential_aln = self.roundInput.elongation.roundDir + f"/ont.potentialExtensionReads.{self.roundInput.elongation.base.tag}.bam"
			ont_input_sequence = self.roundInput.elongation.roundDir + f"/ont.inputCutSequence.fasta"

			# 始终使用单进程 minimap2（benchmark 证明单进程性能更好）
			# Use os.system() like v1 - no timeout limit
			minimap_cmd = f"minimap2 -t {self.roundInput.elongation.base.thread} -Y -ax map-ont {ont_input_sequence} {ont_reads_to_use} | samtools view -bS > {ont_potential_aln}"
			print(f"Executing ONT minimap2 (single-process): {minimap_cmd}")
			result = os.system(minimap_cmd)

			# Check return code and retry if failed (matches v1 behavior)
			if result != 0:
				minimaptag = 1
				while result != 0:
					print(f"ONT minimap2 command execution failed, return code: {result}")
					print(f"Retry {minimaptag} of ONT minimap2 command...")
					result = os.system(minimap_cmd)
					minimaptag += 1
					if minimaptag >= 3:
						print("ONT minimap2 cannot do proper alignment!!!")
						raise Exception("ONT minimap2 failed after 3 retries")

			# Stage 2: ONT minimum threshold filtering
			print("Stage 2: ONT minimum threshold filtering...")
			ont_minimum_aln = self.roundInput.elongation.roundDir + f"/ont.minimumThresholdExtensionReads.{self.roundInput.elongation.base.tag}.bam"
			ont_minimum_reads_id = self.samFilter(ont_potential_aln, ont_minimum_aln, file_prefix="ont",
												 mapping_quality=0, alignment_length=500)

			if not ont_minimum_reads_id or len(ont_minimum_reads_id) == 0:
				print("No ONT reads passed minimum threshold filtering")
				self.ont_extensionReadsNum = 0
				return

			print(f"ont samFilter completed: found {len(ont_minimum_reads_id)} reads")

			# Stage 3: ONT fine filtering with two-level binary search (optimized)
			print("Stage 3: ONT fine filtering with two-level binary search (optimized)...")

			# Get the maximum edge value as upper limit
			max_edge = self.roundInput.elongation.base.edge  # value is 500

			# ============================================================
			# 使用两层二分搜索优化替代原来的线性 while 循环
			# ============================================================
			try:
				# 设置输出文件路径
				ont_selected_aln = self.roundInput.elongation.roundDir + f"/ont.selectPotentialExtensionReads.{self.roundInput.elongation.base.tag}.bam"
				ont_extensionReads_aln = self.roundInput.elongation.roundDir + f"/ont.extensionReads.{self.roundInput.elongation.base.tag}.bam"
				ont_extension_output = self.roundInput.elongation.roundDir + f"/ont.extensionReads.{self.roundInput.elongation.base.tag}.fa"
				
				# 执行两层二分搜索
				success, final_mq, final_el, final_al, final_edge, ext_reads_id = \
					self._binary_search_extension_reads(
						ont_minimum_aln,
						ont_selected_aln,
						ont_extensionReads_aln,
						ont_extension_output,
						"ont",
						max_edge
					)
				
				if success:
					# 复制到最终输出位置
					if os.path.realpath(ont_extension_output) != os.path.realpath(self.ont_extensionReads):
						shutil.copy2(ont_extension_output, self.ont_extensionReads)
						print(f"ONT extension reads copied to: {self.ont_extensionReads}")
					else:
						print(f"ONT extension reads already at target location: {self.ont_extensionReads}")
					
					self.ont_extensionReadsNum = len(ext_reads_id) if ext_reads_id else 0
					print(f"ONT binary search succeeded with {self.ont_extensionReadsNum} extension reads")
				else:
					print("Failed to find ONT extension reads after binary search")
					self.ont_extensionReadsNum = 0
					
			except Exception as e:
				print(f"Error in ONT binary search: {e}")
				import traceback
				traceback.print_exc()
				self.ont_extensionReadsNum = 0

		except Exception as e:
			print(f"Error processing ONT extension reads: {e}")
			import traceback
			traceback.print_exc()
			self.ont_extensionReadsNum = 0

	def checkMixedModeResults(self):
		"""检查混合模式的结果，实现容错机制"""
		if not (hasattr(self.roundInput.elongation.base, 'data_type') and self.roundInput.elongation.base.data_type == 'mixed'):
			return  # 非混合模式，无需检查

		hifi_success = hasattr(self, 'extensionReadsNum') and self.extensionReadsNum > 0
		ont_success = hasattr(self, 'ont_extensionReadsNum') and self.ont_extensionReadsNum > 0

		print(f"混合模式结果检查: HiFi成功={hifi_success}, ONT成功={ont_success}")

		if hifi_success and ont_success:
			print("混合模式：HiFi和ONT都成功，继续混合处理")
			self.mixed_mode_status = 'both_success'
		elif hifi_success and not ont_success:
			print("混合模式：只有HiFi成功，按HiFi单一模式继续")
			self.mixed_mode_status = 'hifi_only'
			# 清理ONT相关文件，避免后续处理混乱
			if hasattr(self, 'ont_extensionReads') and os.path.exists(self.ont_extensionReads):
				try:
					os.remove(self.ont_extensionReads)
				except:
					pass
		elif not hifi_success and ont_success:
			print("混合模式：只有ONT成功，按ONT单一模式继续")
			self.mixed_mode_status = 'ont_only'
		else:
			print("混合模式：HiFi和ONT都失败")
			self.mixed_mode_status = 'both_failed'

	# ============================================================
	# 两层二分搜索优化：用于快速找到最严格的有效参数组合
	# ============================================================
	
	def _generate_edge_values(self, max_edge):
		"""生成所有 Edge 值列表（从10到max_edge，步长10）"""
		return list(range(10, max_edge + 1, 10))
	
	def _generate_inner_combinations(self):
		"""
		生成单个 Edge 块内的所有参数组合（按放宽顺序排列）
		
		放宽顺序：MQ → EL → AL
		- MQ: 20 → 10 → 0
		- EL: 1000 → 900 → ... → 10 (当 MQ=0 时)
		- AL: 3000 → 2900 → ... → 500 (当 MQ=0, EL=10 时)
		
		Returns:
			list of tuples: [(MQ, EL, AL), ...]
		"""
		combinations = []
		
		MQ = 20
		EL = 1000
		AL = 3000
		
		while True:
			combinations.append((MQ, EL, AL))
			
			# 模拟放宽逻辑
			if MQ > 0:
				MQ -= 10
			else:  # MQ == 0
				if EL > 10:
					EL -= 100
				else:  # EL <= 10
					if AL > 500:
						AL -= 100
					else:  # AL <= 500
						break  # 已到最宽松
		
		return combinations
	
	def _test_params_quick(self, input_aln, file_prefix, mq, al, edge):
		"""
		快速测试参数组合（只运行 samFilter + extensionFinder）
		
		Returns:
			int: 找到的 extension reads 数量
		"""
		import tempfile
		import os
		
		# 创建临时文件
		temp_dir = self.roundInput.elongation.roundDir
		temp_select_aln = os.path.join(temp_dir, f"{file_prefix}.temp_select.bam")
		temp_ext_aln = os.path.join(temp_dir, f"{file_prefix}.temp_ext.bam")
		temp_ext_fa = os.path.join(temp_dir, f"{file_prefix}.temp_ext.fa")
		
		try:
			# samFilter
			reads_id = self.samFilter(input_aln, temp_select_aln, 
									  file_prefix=file_prefix,
									  mapping_quality=mq, 
									  alignment_length=al)
			
			if not reads_id or len(reads_id) == 0:
				return 0
			
			# extensionFinder
			ext_reads = self.extensionFinder(temp_select_aln, temp_ext_aln, temp_ext_fa,
											 file_prefix=file_prefix,
											 extension_edge=edge)
			
			return len(ext_reads) if ext_reads else 0
			
		except Exception as e:
			print(f"[_test_params_quick] Error: {e}")
			return 0
		finally:
			# 清理临时文件
			for f in [temp_select_aln, temp_ext_aln, temp_ext_fa]:
				if os.path.exists(f):
					try:
						os.remove(f)
					except:
						pass
	
	def _binary_search_extension_reads(self, input_aln, output_select_aln, output_ext_aln, 
									   output_ext_fa, file_prefix, max_edge):
		"""
		两层二分搜索：快速找到最严格的有效参数组合
		
		第一层：二分查找最小有效 Edge
		第二层：在目标 Edge 内二分查找最严格的有效参数组合
		
		Returns:
			tuple: (success, MQ, EL, AL, Edge, extension_reads_id)
		"""
		print(f"\n[BinarySearch] Starting two-level binary search for {file_prefix}...")
		print(f"[BinarySearch] max_edge={max_edge}")
		
		# 生成 Edge 值列表和内部组合列表
		edge_values = self._generate_edge_values(max_edge)
		inner_combos = self._generate_inner_combinations()
		
		print(f"[BinarySearch] Edge values: {len(edge_values)} ({edge_values[0]} to {edge_values[-1]})")
		print(f"[BinarySearch] Inner combinations per Edge: {len(inner_combos)}")
		print(f"[BinarySearch] Total combinations: {len(edge_values) * len(inner_combos)}")
		
		# ============================================================
		# 第一层：二分查找最小有效 Edge
		# ============================================================
		# 测试每个 Edge 的最宽松组合 (MQ=0, EL=10, AL=500)
		loosest_mq, loosest_el, loosest_al = inner_combos[-1]
		
		print(f"\n[BinarySearch] Layer 1: Finding minimum valid Edge...")
		print(f"[BinarySearch] Testing with loosest params: MQ={loosest_mq}, EL={loosest_el}, AL={loosest_al}")
		
		# 先测试最严格的 Edge
		first_edge = edge_values[0]
		first_result = self._test_params_quick(input_aln, file_prefix, 
											   loosest_mq, loosest_al, first_edge)
		print(f"[BinarySearch] Edge={first_edge} (strictest), loosest params -> {first_result} reads")
		
		if first_result > 0:
			# 最严格的 Edge 就有结果，直接在这个 Edge 内搜索
			target_edge = first_edge
			print(f"[BinarySearch] Found valid reads at strictest Edge={target_edge}")
		else:
			# 测试最宽松的 Edge
			last_edge = edge_values[-1]
			last_result = self._test_params_quick(input_aln, file_prefix,
												  loosest_mq, loosest_al, last_edge)
			print(f"[BinarySearch] Edge={last_edge} (loosest), loosest params -> {last_result} reads")
			
			if last_result == 0:
				# 最宽松都没有结果，直接失败
				print(f"[BinarySearch] No reads found even at loosest Edge={last_edge}, giving up")
				return (False, 0, 10, 500, max_edge, [])
			
			# 二分查找 Edge 边界
			left, right = 0, len(edge_values) - 1
			search_count = 0
			
			while left < right - 1:
				mid = (left + right) // 2
				mid_edge = edge_values[mid]
				
				result = self._test_params_quick(input_aln, file_prefix,
												 loosest_mq, loosest_al, mid_edge)
				search_count += 1
				print(f"[BinarySearch] Edge binary search #{search_count}: Edge={mid_edge} -> {result} reads")
				
				if result > 0:
					right = mid  # 有结果，尝试更严格
				else:
					left = mid   # 无结果，需要更宽松
			
			target_edge = edge_values[right]
			print(f"[BinarySearch] Layer 1 complete: minimum valid Edge={target_edge} (searches: {search_count})")
		
		# ============================================================
		# 第二层：在目标 Edge 内二分查找最严格的有效参数组合
		# ============================================================
		print(f"\n[BinarySearch] Layer 2: Finding strictest valid params within Edge={target_edge}...")
		
		# 先测试最严格的组合
		strictest_mq, strictest_el, strictest_al = inner_combos[0]
		first_inner_result = self._test_params_quick(input_aln, file_prefix,
													 strictest_mq, strictest_al, target_edge)
		print(f"[BinarySearch] Combo[0] (MQ={strictest_mq}, EL={strictest_el}, AL={strictest_al}) -> {first_inner_result} reads")
		
		if first_inner_result > 0:
			# 最严格的组合就有结果
			final_mq, final_el, final_al = strictest_mq, strictest_el, strictest_al
			print(f"[BinarySearch] Found valid reads at strictest combo")
		else:
			# 二分查找内部组合边界
			left, right = 0, len(inner_combos) - 1
			search_count = 0
			
			while left < right - 1:
				mid = (left + right) // 2
				mid_mq, mid_el, mid_al = inner_combos[mid]
				
				result = self._test_params_quick(input_aln, file_prefix,
												 mid_mq, mid_al, target_edge)
				search_count += 1
				print(f"[BinarySearch] Inner binary search #{search_count}: Combo[{mid}] (MQ={mid_mq}, EL={mid_el}, AL={mid_al}) -> {result} reads")
				
				if result > 0:
					right = mid  # 有结果，尝试更严格
				else:
					left = mid   # 无结果，需要更宽松
			
			final_mq, final_el, final_al = inner_combos[right]
			print(f"[BinarySearch] Layer 2 complete: strictest valid combo[{right}] (searches: {search_count})")
		
		# ============================================================
		# 最终执行：用找到的参数生成正式输出文件
		# ============================================================
		print(f"\n[BinarySearch] Final execution with: MQ={final_mq}, EL={final_el}, AL={final_al}, Edge={target_edge}")
		
		# 更新实例变量
		self.selectMappingQuality = final_mq
		self.selectAlignmentLength = final_al
		self.readsExtensionLength = final_el
		self.extensionReadsEdge = target_edge
		
		# 执行最终的 samFilter
		final_reads_id = self.samFilter(input_aln, output_select_aln,
										file_prefix=file_prefix,
										mapping_quality=final_mq,
										alignment_length=final_al)
		self.selectReadsNum = len(final_reads_id) if final_reads_id else 0
		
		# 执行最终的 extensionFinder
		extension_reads_id = self.extensionFinder(output_select_aln, output_ext_aln, output_ext_fa,
												  file_prefix=file_prefix,
												  extension_edge=target_edge)
		
		ext_count = len(extension_reads_id) if extension_reads_id else 0
		print(f"[BinarySearch] Final result: {ext_count} extension reads")
		
		return (ext_count > 0, final_mq, final_el, final_al, target_edge, extension_reads_id)

	def minimumExtensionReads(self):
		# Import required modules
		import os
		import traceback

		self.selectMappingQuality=0
		self.selectAlignmentLength=500
		self.selectNMAlignmentLengthratio=0.1
		self.extensionReadsEdge=self.roundInput.elongation.base.edge
		self.readsExtensionLength=10
		self._minimum_threshold_extension_found = False

		# 根据 data_type 动态选择文件名前缀
		data_type = getattr(self.roundInput.elongation.base, 'data_type', 'hifi')
		if data_type == 'ont':
			file_prefix = 'ont'
		else:
			# HiFi-only 或 Mixed 模式都使用 hifi 前缀
			file_prefix = 'hifi'

		self.minimumThresholdReadsAln=self.roundInput.elongation.roundDir+f"/{file_prefix}.minimumThresholdReads."+self.roundInput.elongation.base.tag+".bam"
		self.minimumThresholdReadsID=self.samFilter(self.potentialExtensionReadsAln,self.minimumThresholdReadsAln, file_prefix=file_prefix)

		# Check if input file exists
		if not os.path.exists(self.minimumThresholdReadsAln):
			print(f"Error: Input file does not exist: {self.minimumThresholdReadsAln}")
			self.minimumThresholdExtensionReadsID = []
			self.note = 'inputFileNotFound'
			return

		# 根据 data_type 动态选择文件名前缀
		self.minimumThresholdExtensionReadsAln=self.roundInput.elongation.roundDir+f"/{file_prefix}.minimumThresholdExtensionReads."+self.roundInput.elongation.base.tag+".bam"
		self.minimumThresholdExtensionReads=self.roundInput.elongation.roundDir+f"/{file_prefix}.minimumThresholdExtensionReads."+self.roundInput.elongation.base.tag+".fa"

		try:
			print("Calling extensionFinder to find minimum threshold extension reads...")
			self.minimumThresholdExtensionReadsID=self.extensionFinder(
				self.minimumThresholdReadsAln,
				self.minimumThresholdExtensionReadsAln,
				self.minimumThresholdExtensionReads,
				file_prefix=file_prefix
			)
			print(f"Found {len(self.minimumThresholdExtensionReadsID)} minimum threshold extension reads")
		except Exception as e:
			print(f"Error finding minimum threshold extension reads: {str(e)}")
			traceback.print_exc()
			self.minimumThresholdExtensionReadsID = []
			print("Will continue processing, but may affect result quality")

		if hasattr(self, 'minimumThresholdExtensionReadsID') and len(self.minimumThresholdExtensionReadsID)>0:
			self._minimum_threshold_extension_found = True
			print(f"Found {len(self.minimumThresholdExtensionReadsID)} extension reads at minimum threshold")
		else:
			print(f"Info: No extension reads found at minimum threshold. This is normal and will try alternative approaches.")
		self.note=''

	# Modified extensionFinder method in FindExtensionReads.py
	def extensionFinder(self, inputAln, outputAln, outputSeq, file_prefix="", extension_edge=None):
		import pysam
		from pysam import AlignmentFile
		outputSeqFile=open(outputSeq,'w')
		inputAlnFile=AlignmentFile(inputAln,'rb')
		outputAlnFile=AlignmentFile(outputAln,'wb',template=inputAlnFile)
		readslist=[]

		# 动态选择正确的readsDict
		if file_prefix == 'ont' and hasattr(self.roundInput.elongation.base, 'ont_readsDict') and self.roundInput.elongation.base.ont_readsDict is not None:
			# ONT处理：使用ONT专用索引
			readsDict = self.roundInput.elongation.base.ont_readsDict
			print(f"[extensionFinder] 使用ONT专用索引进行{file_prefix}数据处理")
		else:
			# HiFi处理或混合模式降级：使用主索引（HiFi索引）
			readsDict = self.roundInput.elongation.base.readsDict
			print(f"[extensionFinder] 使用主索引进行{file_prefix}数据处理")
		
		# Verify readsDict is usable (should already be loaded by TelSeeker.__init__)
		if readsDict is None:
			print(f"[extensionFinder] ERROR: readsDict is None for {file_prefix} data")
			print(f"[extensionFinder] Checking base object attributes:")
			print(f"[extensionFinder]   hasattr ont_readsDict: {hasattr(self.roundInput.elongation.base, 'ont_readsDict')}")
			print(f"[extensionFinder]   hasattr readsDict: {hasattr(self.roundInput.elongation.base, 'readsDict')}")
			if hasattr(self.roundInput.elongation.base, 'ont_readsDict'):
				print(f"[extensionFinder]   ont_readsDict value: {self.roundInput.elongation.base.ont_readsDict}")
			if hasattr(self.roundInput.elongation.base, 'readsDict'):
				print(f"[extensionFinder]   readsDict value: {self.roundInput.elongation.base.readsDict}")
			raise ValueError("readsDict is None, cannot proceed with extension finding")
		
		# Critical fix: Load readsDict if it's still a file path string (shouldn't happen if TelSeeker.__init__ worked)
		if isinstance(readsDict, str):
			print(f"[extensionFinder] Warning: readsDict is still a file path string: {readsDict}")
			print(f"[extensionFinder] This indicates TelSeeker.__init__ did not load the index properly")
			print(f"[extensionFinder] Attempting to load readsDict from index file...")
			try:
				# Use Bio.SeqIO.index_db to open the SQLite index
				from Bio import SeqIO
				if readsDict.endswith('.idx'):
					# It's an index database file
					readsDict = SeqIO.index_db(readsDict)
					print(f"[extensionFinder] Successfully loaded readsDict from index_db")
				else:
					# It's a FASTA file
					readsDict = SeqIO.index(readsDict, 'fasta')
					print(f"[extensionFinder] Successfully loaded readsDict from FASTA file")
				print(f"[extensionFinder] ReadsDict type: {type(readsDict).__name__}, contains {len(readsDict)} entries")
			except Exception as e:
				print(f"[extensionFinder] Error loading readsDict: {str(e)}")
				import traceback
				traceback.print_exc()
				raise ValueError(f"Cannot load readsDict from path: {readsDict}")
		
		# Final verification
		if isinstance(readsDict, str):
			raise ValueError(f"readsDict is still a string after loading attempt: {readsDict}")
		
		print(f"[extensionFinder] {file_prefix} readsDict ready: type={type(readsDict).__name__}, entries={len(readsDict)}")

		# Use provided extension_edge or default value
		if extension_edge is not None:
			edge_value = extension_edge
		else:
			edge_value = self.extensionReadsEdge
		
		print(f"[extensionFinder] {file_prefix} Processing with parameters:")
		print(f"[extensionFinder]   edge_value: {edge_value}")
		print(f"[extensionFinder]   readsExtensionLength: {self.readsExtensionLength}")
		print(f"[extensionFinder]   usedReads count: {len(self.usedReads)}")
		print(f"[extensionFinder]   readsDict type: {type(readsDict).__name__}")
		
		# Counters for debugging
		total_reads = 0
		filter_stats = {
			'keyError': 0,
			'extensionTooShort': 0,
			'queryDistTooLarge': 0,
			'refDistTooLarge': 0,
			'inUsedReads': 0,
			'inReadslist': 0,
			'passed': 0
		}

		# ===== Core modification: restore 1.0's direct memory access method =====
		for r in inputAlnFile:
			total_reads += 1
			queryID = r.query_name

			# 直接使用原始 queryID，不做任何前缀处理
			# 理由：
			# 1. K-mer过滤不会添加前缀（经代码审查确认）
			# 2. reads文件中的ID = 索引中的key = BAM中的query_name
			# 3. 不需要任何ID转换
			original_queryID = queryID

			# 使用动态选择的readsDict进行查找
			try:
				query = readsDict[original_queryID]
			except KeyError:
				filter_stats['keyError'] += 1
				if total_reads <= 10:  # Only print first 10 errors
					print(f"[extensionFinder] Warning: Cannot find ID {original_queryID} in {file_prefix} readsDict")
				continue

			# Calculate boundary distance (maintain 1.0 logic)
			# 根据file_prefix确定数据类型
			data_type = 'ont' if file_prefix == 'ont' else 'hifi'
			queryDistance, refDistance, extensionLength, extensionReadsSeq = self.calculateBoundDistance(
				original_queryID, query, r, data_type
			)

			# Debug: print first 5 reads' details
			if total_reads <= 5:
				print(f"[extensionFinder] Read #{total_reads}: {original_queryID}")
				print(f"[extensionFinder]   queryDistance={queryDistance}, refDistance={refDistance}, extensionLength={extensionLength}")
				print(f"[extensionFinder]   extensionLength>={self.readsExtensionLength}? {extensionLength >= self.readsExtensionLength}")
				print(f"[extensionFinder]   queryDistance<={edge_value}? {queryDistance <= edge_value}")
				print(f"[extensionFinder]   refDistance<={edge_value}? {refDistance <= edge_value}")
				print(f"[extensionFinder]   not in usedReads? {original_queryID not in self.usedReads}")

			# Condition judgment (maintain 1.0 logic)
			if self.readsExtensionLength <= extensionLength:
				if queryDistance <= edge_value and refDistance <= edge_value:
					if original_queryID not in self.usedReads:
						if original_queryID not in readslist:
							l = '>' + original_queryID + "\n" + str(query.seq) + "\n"
							outputSeqFile.writelines(l)
							readslist.append(original_queryID)
							filter_stats['passed'] += 1
						else:
							filter_stats['inReadslist'] += 1
						outputAlnFile.write(r)
					else:
						filter_stats['inUsedReads'] += 1
				else:
					if queryDistance > edge_value:
						filter_stats['queryDistTooLarge'] += 1
					if refDistance > edge_value:
						filter_stats['refDistTooLarge'] += 1
			else:
				filter_stats['extensionTooShort'] += 1
		# ===== End of modification =====

		outputSeqFile.close()
		inputAlnFile.close()
		outputAlnFile.close()
		
		# Print filtering statistics
		print(f"[extensionFinder] === Filtering Statistics ===")
		print(f"[extensionFinder] Total reads processed: {total_reads}")
		print(f"[extensionFinder] Passed all filters: {filter_stats['passed']}")
		print(f"[extensionFinder] Filtered by:")
		print(f"[extensionFinder]   - KeyError (ID not found): {filter_stats['keyError']}")
		print(f"[extensionFinder]   - Extension too short: {filter_stats['extensionTooShort']}")
		print(f"[extensionFinder]   - queryDistance > {edge_value}: {filter_stats['queryDistTooLarge']}")
		print(f"[extensionFinder]   - refDistance > {edge_value}: {filter_stats['refDistTooLarge']}")
		print(f"[extensionFinder]   - Already in usedReads: {filter_stats['inUsedReads']}")
		print(f"[extensionFinder]   - Already in readslist: {filter_stats['inReadslist']}")
		print(f"[extensionFinder] ===========================")

		# Memory cleanup
		import gc
		gc.collect()

		return readslist
	def calculateBoundDistance(self,queryID,query,r,data_type='hifi'):
		if r.is_reverse:
			queryseq=query.seq.reverse_complement()
		else:
			queryseq=query.seq

		# 根据数据类型选择合适的种子序列
		if data_type == 'ont' and hasattr(self.roundInput, 'ontInputSeq'):
			# 为ONT reads使用ONT种子序列
			ont_seed_file = self.roundInput.ontInputSeq
			ont_seed_sequence = None
			for gseq in SeqIO.parse(ont_seed_file, 'fasta'):
				ont_seed_sequence = gseq
				break
			seed_sequence = ont_seed_sequence if ont_seed_sequence else self.roundInput.inputSeedSequence
		else:
			# 默认使用HiFi种子序列
			seed_sequence = self.roundInput.inputSeedSequence

		qs,qe,rs,re=self.findAlnPosition(queryseq,seed_sequence,r)
		if self.roundInput.elongation.base.flag=='left':
			queryDistance=qs
			extensionReadsSeq=queryseq
			refDistance=len(seed_sequence.seq)-re
			extensionLength=len(queryseq)-qe
		else:
			queryDistance=len(queryseq)-qe
			extensionReadsSeq=queryseq
			refDistance=rs
			extensionLength=qs
		if qs<0 or len(queryseq)<qe or qe<0 or rs<0 or re<0 :#or len(self.roundInput.inputSeedSequence.seq)<re:
			print ('wrong sequence end',qs,qe,rs,re)
			print (queryDistance,refDistance,extensionLength,extensionReadsSeq)
			print (qs<0)
			print (len(queryseq)<qe)
			print (qe<0)
			print (rs<0)
			print (re<0)
			print (len(self.roundInput.inputSeedSequence.seq)<re)
			print (len(self.roundInput.inputSeedSequence.seq),re)
			sys.exit()
		return queryDistance,refDistance,extensionLength,extensionReadsSeq

	def findAlnPosition(self,queryseq,refseq,r):
		ct=r.cigartuples
		scpstart=ct[0]
		if scpstart[0]==4:
			scps=scpstart[1]
		else:
			scps=0

		scpend=ct[-1]
		if scpend[0]==4:
			scpe=scpend[1]
		else:
			scpe=0

		if queryseq==r.query_sequence or r.query_alignment_sequence==None:
			qs=r.query_alignment_start
			qe=r.query_alignment_end
		else:
			qaln=r.query_alignment_sequence
			qs=str(queryseq).index(qaln)
			qe=qs+len(r.query_alignment_sequence)
		rs=r.reference_start
		re=r.reference_end
		if qs<0:
			print ('wrong query start',qs)
		if qe>len(queryseq):
			print ('wrong query end',qe,len(queryseq))
		return qs,qe,rs,re



	def create_bam_index(self, bam_file):
		"""
		Create index for BAM file with automatic sorting if needed
		"""
		import subprocess
		import shutil

		if not os.path.exists(bam_file) or os.path.getsize(bam_file) == 0:
			print(f"Warning: BAM file does not exist or is empty: {bam_file}")
			return False

		try:
			print(f"Creating BAM index for {bam_file}...")
			# First try to create index directly
			index_cmd = f"samtools index {bam_file}"
			index_result = subprocess.run(index_cmd, shell=True, timeout=300, capture_output=True)
			if index_result.returncode == 0:
				print(f"BAM index created successfully")
				return True
			else:
				# If direct indexing fails, try sorting first
				print(f"Direct indexing failed, attempting to sort BAM file first...")
				sorted_bam = bam_file.replace('.bam', '.sorted.bam')
				sort_cmd = f"samtools sort {bam_file} -o {sorted_bam}"
				sort_result = subprocess.run(sort_cmd, shell=True, timeout=600, capture_output=True)
				if sort_result.returncode == 0:
					# Replace original with sorted version
					shutil.move(sorted_bam, bam_file)
					# Try indexing again
					index_result2 = subprocess.run(index_cmd, shell=True, timeout=300, capture_output=True)
					if index_result2.returncode == 0:
						print(f"BAM index created successfully after sorting")
						return True
					else:
						print(f"Warning: Failed to create BAM index even after sorting: {index_result2.stderr.decode('utf-8', errors='ignore')}")
						return False
				else:
					print(f"Warning: Failed to sort BAM file: {sort_result.stderr.decode('utf-8', errors='ignore')}")
					return False
		except Exception as e:
			print(f"Warning: Exception while creating BAM index: {e}")
			return False

	def cleanup_multiplier_temp_dirs(self):
		"""清理multiplier循环的临时目录"""
		import shutil
		import subprocess
		
		output_dir = self.roundInput.elongation.roundDir
		temp_dirs = [
			os.path.join(output_dir, "temp_kmer_filter_1"),
			os.path.join(output_dir, "temp_kmer_filter_1_output_reads_part")
		]
		
		for temp_dir in temp_dirs:
			if os.path.exists(temp_dir):
				try:
					shutil.rmtree(temp_dir)
					print(f"✓ 已清理临时目录: {os.path.basename(temp_dir)}")
				except Exception as e:
					print(f"⚠ shutil删除失败: {e}，尝试rm命令")
					try:
						subprocess.run(f"rm -rf {temp_dir}", shell=True, check=True, timeout=30)
						print(f"✓ rm命令清理成功: {os.path.basename(temp_dir)}")
					except Exception as e2:
						print(f"✗ 清理失败 {os.path.basename(temp_dir)}: {e2}")

	def samFilter(self,inputAln,outputAln, file_prefix="", mapping_quality=None, alignment_length=None, nm_ratio=None):
		samFile=AlignmentFile(inputAln,"rb",check_sq=False)
		outputBamFile=AlignmentFile(outputAln,"wb", template=samFile)

		readslist=[]
		print (f"{file_prefix} samFilter processing: {inputAln}")
		# Use provided parameters or fall back to instance variables
		sMQ = mapping_quality if mapping_quality is not None else self.selectMappingQuality
		sAlignmentLength = alignment_length if alignment_length is not None else self.selectAlignmentLength
		sNMAlignmentLengthr = nm_ratio if nm_ratio is not None else self.selectNMAlignmentLengthratio

		for r in samFile:
			if r.is_unmapped==False and r.mapping_quality>=sMQ:
				for i in r.tags:
					if i[0]=='NM':
						NM=i[1]
				AlignmentLength=len(r.query_alignment_sequence)
				if  AlignmentLength>=sAlignmentLength and float(NM)/AlignmentLength<=sNMAlignmentLengthr:
					outputBamFile.write(r)
					if r.query_name not in readslist:
						readslist.append(r.query_name)
		samFile.close()
		outputBamFile.close()
		print(f"{file_prefix} samFilter completed: found {len(readslist)} reads")

		return readslist

	def extract_kmers_simple(self, kmerseq, kmer_size, kmer_num, interval=None):
		"""
		简化版kmer提取：从靠近gap的末端开始，以指定间隔提取kmer
		
		注意：只提取 forward kmer，不生成反向互补序列
		反向互补序列将在频次统计和搜索阶段动态生成
		
		Parameters:
			kmerseq: Sequence to extract k-mers from
			kmer_size: Length of k-mer
			kmer_num: Number of k-mers to extract
			interval: Interval between kmers (default: 9*kmer_size)
		
		Returns:
			List of k-mer sequences (forward only)
		"""
		# Import required modules
		import os

		# Create output directory (if it doesn't exist)
		output_dir = self.roundInput.elongation.roundDir
		if not os.path.exists(output_dir):
			os.makedirs(output_dir)
		
		# K-mer extraction step: kmer_size + interval
		if interval is None:
			interval = 9 * kmer_size
		step_size = kmer_size + interval

		# Record original sequence length
		seq_length = len(kmerseq)
		print(f"Original sequence length: {seq_length} bp")
		print(f"Extracting {kmer_num} k-mers with interval={interval} bp (step={step_size} bp)")

		# If sequence is too short, cannot extract k-mer
		if seq_length < kmer_size:
			print(f"Warning: Sequence length ({seq_length}) is smaller than k-mer size ({kmer_size}), cannot extract k-mer")
			return None

		# Get flag to determine extraction direction
		flag = self.roundInput.elongation.base.flag
		
		# Extract k-mers with 9*kmer_size interval
		kmers = []
		
		if flag == 'left':
			# gap在右端，从右侧开始向左提取
			print(f"flag='left': gap在右端，从右侧开始向左提取k-mer（间隔{interval} bp）")
			start_pos = seq_length - kmer_size
			
			for i in range(kmer_num):
				pos = start_pos - (i * step_size)
				if pos < 0:
					print(f"Note: Reached sequence start, extracted {i} k-mers")
					break
				kmer = kmerseq[pos:pos + kmer_size]
				kmers.append(kmer)
				
				# Print first 5 and last 5 k-mers for verification
				if i < 5 or i >= kmer_num - 5:
					print(f"K-mer {i+1}: position {pos}, sequence: {kmer[:20]}...")
					
		else:  # flag == 'right'
			# gap在左端，从左侧开始向右提取
			print(f"flag='right': gap在左端，从左侧开始向右提取k-mer（间隔{interval} bp）")
			
			for i in range(kmer_num):
				pos = i * step_size
				if pos + kmer_size > seq_length:
					print(f"Note: Reached sequence end, extracted {i} k-mers")
					break
				kmer = kmerseq[pos:pos + kmer_size]
				kmers.append(kmer)
				
				# Print first 5 and last 5 k-mers for verification
				if i < 5 or i >= kmer_num - 5:
					print(f"K-mer {i+1}: position {pos}, sequence: {kmer[:20]}...")

		print(f"Extracted {len(kmers)} k-mers with interval={interval} bp (forward only)")

		# De-duplicate k-mers
		unique_kmers = set()
		for kmer in kmers:
			uppercase_kmer = str(kmer).upper()
			unique_kmers.add(uppercase_kmer)
		
		print(f"After de-duplication: {len(unique_kmers)} unique k-mers (removed {len(kmers) - len(unique_kmers)} duplicates)")
		print(f"Note: Reverse complement sequences will be generated during frequency counting")
		
		# Return list of unique k-mer sequences (forward only)
		return sorted(list(unique_kmers))

	def write_kmer_filtering_log(self, log_data):
		"""写入k-mer过滤日志"""
		import os
		import datetime

		# 创建日志文件路径
		output_dir = self.roundInput.elongation.roundDir
		log_file = os.path.join(output_dir, "kmer_filtering.log")

		# 获取当前时间
		current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

		# 写入日志
		with open(log_file, 'a', encoding='utf-8') as f:
			f.write(f"\n{'='*80}\n")
			f.write(f"K-mer过滤日志 - {current_time}\n")
			f.write(f"Round: {getattr(self.roundInput.elongation, 'roundNum', 'Unknown')}\n")
			f.write(f"Flag: {self.roundInput.elongation.base.flag}\n")
			f.write(f"{'='*80}\n")

			# 写入具体日志数据
			for section, content in log_data.items():
				f.write(f"\n[{section}]\n")
				if isinstance(content, dict):
					for key, value in content.items():
						f.write(f"{key}: {value}\n")
				elif isinstance(content, list):
					for i, item in enumerate(content, 1):
						f.write(f"{i:3d}. {item}\n")
				else:
					f.write(f"{content}\n")

			f.write(f"\n{'='*80}\n\n")

		print(f"K-mer过滤日志已写入: {log_file}")

	def seqkit(self, kmer_list, reads, output_suffix=""):
		"""
		Call seqkit grep command to extract sequences containing specified k-mers from kmer_list in reads
		Use GNU parallel to process split reads files in parallel, improving processing speed

		Parameters:
			kmer_list: File path containing k-mers
			reads: Reads file path to search

		Returns:
			Output file path
		"""
		# Import required modules
		import subprocess
		import os
		import glob
		import time
		import shutil

		# Ensure using absolute paths
		kmer_list = os.path.abspath(kmer_list)
		reads = os.path.abspath(reads)

		print(f"seqkit function using absolute paths: kmer_list={kmer_list}, reads={reads}")

		# Create output directory (if it doesn't exist)
		output_dir = self.roundInput.elongation.roundDir
		if not os.path.exists(output_dir):
			os.makedirs(output_dir)

		# Create temporary output directory with suffix-specific naming
		if output_suffix:
			seqkit_tmp_dir = os.path.join(output_dir, f"seqkit_tmp_{output_suffix}")
		else:
			seqkit_tmp_dir = os.path.join(output_dir, "seqkit_tmp_hifi")
		if not os.path.exists(seqkit_tmp_dir):
			os.makedirs(seqkit_tmp_dir)

		# Set final output file path with optional suffix
		if output_suffix:
			output_file = os.path.join(output_dir, f"seqkitOutput.{output_suffix}.fa")
		else:
			output_file = os.path.join(output_dir, "seqkitOutput.fa")

		# Get split reads file paths
		# Use out parameter passed during initialization to get DEGAP.py output directory
		if self.out:
			# If out parameter was provided during initialization, use it first
			base_out_dir = os.path.abspath(self.out)
		else:
			# Try to get from other attributes
			base_out_dir = None
			if hasattr(self.roundInput.elongation.base, "out"):
				base_out_dir = os.path.abspath(self.roundInput.elongation.base.out)
			elif hasattr(self.roundInput.elongation, "out"):
				base_out_dir = os.path.abspath(self.roundInput.elongation.out)

			# If still unable to get, use current working directory as fallback
			if not base_out_dir:
				base_out_dir = os.path.abspath(os.getcwd())
				print(f"Warning: Could not determine base output directory, using current directory: {base_out_dir}")

		# For ctglinker mode, the reads_part directory is in the main output directory
		# We need to traverse up to find the main output directory containing reads_part
		reads_part_dir = None
		current_dir = base_out_dir

		# Try to find hifi_reads_part directory by traversing up the directory tree
		for _ in range(5):  # Limit search depth to avoid infinite loop
			potential_reads_part = os.path.join(current_dir, "hifi_reads_part")
			if os.path.exists(potential_reads_part):
				reads_part_dir = potential_reads_part
				break
			# Backward compatibility: also check for old naming
			potential_old_reads_part = os.path.join(current_dir, "reads_part")
			if os.path.exists(potential_old_reads_part):
				reads_part_dir = potential_old_reads_part
				print(f"Found old-format reads_part directory: {reads_part_dir}")
				break
			parent_dir = os.path.dirname(current_dir)
			if parent_dir == current_dir:  # Reached root directory
				break
			current_dir = parent_dir

		# If not found by traversing up, use the unified naming logic
		if not reads_part_dir:
			reads_part_dir = os.path.join(base_out_dir, "hifi_reads_part")

		print(f"Using reads_part directory: {reads_part_dir}")

		# Find split files
		reads_files = glob.glob(f"{reads_part_dir}/*.fasta")

		if not reads_files:
			reads_files = glob.glob(f"{reads_part_dir}/*.fa*")

		if not reads_files:
			# If split reads files are not found, use original method
			print(f"Warning: No split read files found in {reads_part_dir}, using original read file")
			cmd = f"seqkit grep -f {kmer_list} -s {reads} > {output_file}"

			try:
				process = subprocess.run(cmd, shell=True, check=True)
				print(f"Seqkit completed with single file")
				return str(output_file)
			except subprocess.CalledProcessError as e:
				print(f"Seqkit command failed: {e}")
				raise

		print(f"Found {len(reads_files)} split read files in {reads_part_dir}")

		# Clean up possibly existing old output files
		for old_file in glob.glob(f"{seqkit_tmp_dir}/*.output.fasta"):
			try:
				os.remove(old_file)
			except:
				pass

		# Create log file for parallel tasks
		parallel_log = os.path.join(output_dir, "parallel_seqkit.log")

		# 1. Use GNU parallel to process split reads files in parallel, capturing output and exit status
		print("Starting parallel processing of split read files...")
		try:
			# Use --joblog parameter to record job status
			# Use thread parameter from base object for parallel control
			thread_num = self.roundInput.elongation.base.thread
			parallel_cmd = f"parallel --joblog {output_dir}/parallel_jobs.log -j {thread_num} 'seqkit grep -f {kmer_list} -s {{}} -o {seqkit_tmp_dir}/{{/.}}.output.fasta' ::: {reads_part_dir}/*.fa*"

			print(f"Running parallel seqkit with command: {parallel_cmd}")
			# Capture standard output and error output
			result = subprocess.run(
				parallel_cmd,
				shell=True,
				check=True,
				stdout=subprocess.PIPE,
				stderr=subprocess.PIPE,
				text=True
			)

			# Print command output information
			if result.stdout:
				print("Parallel command output:")
				print(result.stdout[:1000] + "..." if len(result.stdout) > 1000 else result.stdout)

			if result.stderr:
				print("Parallel command warnings/errors:")
				print(result.stderr[:1000] + "..." if len(result.stderr) > 1000 else result.stderr)

			print(f"GNU parallel command completed with return code {result.returncode}")

			# Check parallel-generated joblog file to confirm all tasks are completed
			if os.path.exists(f"{output_dir}/parallel_jobs.log"):
				with open(f"{output_dir}/parallel_jobs.log", 'r') as log_file:
					lines = log_file.readlines()
					# Skip header line
					data_lines = [line for line in lines if line.strip() and not line.startswith("#")]
					completed_jobs = len(data_lines)
					print(f"Parallel jobs completed: {completed_jobs}/{len(reads_files)}")

					# Modify logic for determining task failure: exitval=0 means success
					failed_jobs = []
					for line in data_lines:
						cols = line.split("\t")
						if len(cols) >= 7:  # Ensure at least 7 columns
							exitval = cols[6].strip()
							if exitval != "0":  # Only consider failure when exitval is not 0
								failed_jobs.append(line)

					if failed_jobs:
						print(f"Warning: {len(failed_jobs)} parallel jobs failed with non-zero exit codes")
						# Can add more detailed failure reason analysis
						for i, job in enumerate(failed_jobs[:3]):  # Only show first 3 failed tasks
							print(f"  Failed job {i+1}: {job.strip()}")
						if len(failed_jobs) > 3:
							print(f"  ... and {len(failed_jobs)-3} more failures")

		except subprocess.CalledProcessError as e:
			print(f"Parallel seqkit command failed with return code {e.returncode}")
			print(f"Error output: {e.stderr if hasattr(e, 'stderr') else 'No error output available'}")
			if os.path.exists(f"{output_dir}/parallel_jobs.log"):
				print("Checking job log for partial results...")
				# Even if command fails, we try to process possible partial results
			else:
				print("No job log found, parallel execution may have failed completely")
				raise

		# Wait a short time to ensure all files are written completely
		time.sleep(5)

		# 2. Merge results
		output_files = glob.glob(f"{seqkit_tmp_dir}/*.output.fasta")

		if not output_files:
			print("Warning: No output files were generated from parallel seqkit")
			# Possibly no matches, create an empty file
			open(output_file, 'w').close()
			return str(output_file)

		print(f"Merging {len(output_files)} output files...")

		# Use cat command to merge files
		try:
			merge_cmd = f"cat {seqkit_tmp_dir}/*.output.fasta > {output_file}"
			print(f"Merging results with command: {merge_cmd}")
			process = subprocess.run(merge_cmd, shell=True, check=True)
			print(f"Successfully merged {len(output_files)} output files")
		except subprocess.CalledProcessError as e:
			print(f"Merge command failed: {e}")

			# If cat command fails, try using Python to merge files
			try:
				print("Attempting to merge files using Python...")
				with open(output_file, 'w') as outf:
					for f in output_files:
						with open(f, 'r') as inf:
							shutil.copyfileobj(inf, outf)
				print("Python file merge successful")
			except Exception as e2:
				print(f"Python merge also failed: {e2}")
				raise

		# 3. Clean up intermediate files
		try:
			subprocess.run(f"rm -r {seqkit_tmp_dir}", shell=True, check=True)
			print(f"Cleaned up temporary files in {seqkit_tmp_dir}")
		except subprocess.CalledProcessError as e:
			print(f"Warning: Failed to clean up temporary files: {e}")

		# Check output file
		if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
			print(f"Seqkit completed successfully, output file size: {os.path.getsize(output_file)} bytes")
		else:
			print(f"Warning: Seqkit output file is empty or doesn't exist")

		return str(output_file)

	def _count_kmers_in_parts_using_rg(self, kmer_list, parts_list):
		"""
		使用 rg 统计 kmer（包含 rc）在各分片中的频次
		参照 test_rg_01.sh 的逻辑：kmer + rc 作为一个整体统计
		保持与 jellyfish 版本相同的 parallel 框架
		
		Parameters:
			kmer_list: 要统计的kmer列表（只包含 forward kmer）
			parts_list: reads分片文件列表
			
		Returns:
			dict: {kmer: total_count}  # total_count = count(kmer) + count(rc)
		"""
		import os
		import subprocess
		import time
		import glob
		from collections import defaultdict

		if not kmer_list or not parts_list:
			return {}

		print(f"\n[K-mer Count] 开始使用 rg 统计{len(kmer_list)}个kmer（包含rc）在{len(parts_list)}个分片中的频次...")
		start_time = time.time()

		output_dir = self.roundInput.elongation.roundDir
		temp_count_dir = os.path.join(output_dir, "temp_rg_counts")
		if os.path.exists(temp_count_dir):
			import shutil
			shutil.rmtree(temp_count_dir)
		os.makedirs(temp_count_dir)

		# 1. 生成反向互补函数并创建 kmer + rc 查询文件
		def reverse_complement(seq):
			"""生成DNA序列的反向互补"""
			trans = str.maketrans('ATCGatcg', 'TAGCtagc')
			return seq.translate(trans)[::-1]

		# 生成 kmer + rc 的完整列表（去重）
		kmer_with_rc = set()
		for kmer in kmer_list:
			kmer_with_rc.add(kmer)
			kmer_with_rc.add(reverse_complement(kmer))

		query_file = os.path.join(temp_count_dir, "query_kmers.txt")
		with open(query_file, 'w') as f:
			for seq in sorted(kmer_with_rc):
				f.write(f"{seq}\n")

		print(f"  生成了 {len(kmer_with_rc)} 个唯一序列（包含原始和反向互补）")

		# 2. 创建 parallel 脚本（参照 test_rg_01.sh）
		script_path = os.path.join(temp_count_dir, "count_part.sh")
		with open(script_path, 'w') as f:
			f.write("#!/bin/bash\n")
			f.write("set -e\n")
			f.write("PART_FILE=\"$1\"\n")
			f.write(f"QUERY_FILE=\"{query_file}\"\n")
			f.write(f"OUTPUT_DIR=\"{temp_count_dir}\"\n")
			f.write("BASENAME=$(basename \"$PART_FILE\")\n")
			f.write("COUNT_FILE=\"$OUTPUT_DIR/${BASENAME}.counts\"\n")
			f.write("\n")
			# 使用 rg 搜索并统计频次（参照 test_rg_01.sh 的逻辑）
			f.write("# 使用 rg 搜索所有序列并统计频次\n")
			f.write("rg -o -F -I -f \"$QUERY_FILE\" \"$PART_FILE\" 2>/dev/null | sort | uniq -c | awk '{print $2, $1}' > \"$COUNT_FILE\" || touch \"$COUNT_FILE\"\n")

		os.chmod(script_path, 0o755)

		# 3. 准备分片列表文件
		parts_list_file = os.path.join(temp_count_dir, "parts_list.txt")
		with open(parts_list_file, 'w') as f:
			for part in parts_list:
				f.write(f"{part}\n")

		# 4. 并行执行（与 jellyfish 版本完全一致）
		thread_num = self.roundInput.elongation.base.thread
		parallel_cmd = f"parallel --will-cite -j {thread_num} bash {script_path} :::: {parts_list_file}"

		try:
			subprocess.run(parallel_cmd, shell=True, check=True)
		except subprocess.CalledProcessError as e:
			print(f"Warning: rg counting parallel execution failed: {e}")
			return {}

		# 5. 合并结果 - 先统计每个序列（kmer或rc）的总频次
		seq_counts = defaultdict(int)  # 存储每个序列的总频次
		count_files = glob.glob(os.path.join(temp_count_dir, "*.counts"))

		print(f"  处理完成，合并{len(count_files)}个统计文件...")

		for cfile in count_files:
			if os.path.getsize(cfile) == 0:
				continue
			try:
				with open(cfile, 'r') as f:
					for line in f:
						parts = line.strip().split()
						if len(parts) == 2:
							seq = parts[0]
							count = int(parts[1])
							seq_counts[seq] += count
			except Exception as e:
				print(f"Warning: error reading count file {cfile}: {e}")

		# 6. 为每个原始 kmer 合并频数（kmer + rc）
		kmer_total_counts = {}
		for kmer in kmer_list:
			rc = reverse_complement(kmer)
			total = seq_counts.get(kmer, 0) + seq_counts.get(rc, 0)
			if total > 0:  # 只保留频数 > 0 的
				kmer_total_counts[kmer] = total

		print(f"  合并 kmer+rc 频数：{len(kmer_total_counts)} 个 kmer 有匹配（总提交 {len(kmer_list)} 个）")

		# 7. 清理临时目录
		try:
			import shutil
			shutil.rmtree(temp_count_dir)
		except:
			pass

		elapsed = time.time() - start_time
		print(f"[K-mer Count] 统计完成，耗时{elapsed:.2f}秒")

		# Memory cleanup
		del seq_counts, kmer_with_rc
		import gc
		gc.collect()

		return kmer_total_counts

	def _run_kmer_filter_for_platform(self, kmerseq, flag, parts, platform, output_dir, kmer_file, kmer_list_expanded, thread_num):
		"""
		对单个平台（HiFi 或 ONT）执行独立的 K-mer 过滤流程
		
		Parameters:
			kmerseq: 种子序列
			flag: left 或 right
			parts: 该平台的分片文件列表
			platform: 'hifi' 或 'ont'
			output_dir: 输出目录
			kmer_file: 初始 K-mer 文件路径
			kmer_list_expanded: 扩展后的 K-mer 列表
			thread_num: 并行线程数
			
		Returns:
			(output_file, read_count, top1_count, low_freq_count, high_freq_count) 或 (None, 0, 0, 0, 0) 失败时
		"""
		import os
		import subprocess
		import glob
		import time
		
		if not parts:
			print(f"[{platform.upper()}] 无分片文件，跳过")
			return None, 0, 0, 0, 0
		
		print(f"\n{'='*60}")
		print(f"[{platform.upper()}] 开始独立 K-mer 过滤（{len(parts)} 个分片）")
		print(f"{'='*60}")
		
		# 创建平台专用的临时目录
		stage1_dir = os.path.join(output_dir, f"temp_{platform}_stage1")
		stage2_dir = os.path.join(output_dir, f"temp_{platform}_stage2")
		
		import shutil
		for d in [stage1_dir, stage2_dir]:
			if os.path.exists(d):
				shutil.rmtree(d)
			os.makedirs(d)
		
		# Step 1: 第一阶段粗筛提取
		print(f"[{platform.upper()}] Step 1: 粗筛提取...")
		stage1_script = os.path.join(output_dir, f"{platform}_stage1.sh")
		with open(stage1_script, 'w') as f:
			f.write("#!/bin/bash\n")
			f.write("set -e\n")
			f.write("PART_FILE=\"$1\"\n")
			f.write(f"KMER_FILE=\"{kmer_file}\"\n")
			f.write(f"OUTPUT_DIR=\"{stage1_dir}\"\n")
			f.write("BASENAME=$(basename \"$PART_FILE\")\n")
			f.write("RG_OUT=\"$OUTPUT_DIR/${BASENAME}.rough.fa\"\n")
			f.write("TOP1_OUT=\"$OUTPUT_DIR/${BASENAME}.top1.fa\"\n")
			f.write("TEMP_OUT=\"$OUTPUT_DIR/${BASENAME}.temp.fa\"\n")
			f.write("rg -f \"$KMER_FILE\" -F -B 1 -N -I \"$PART_FILE\" | grep -v '^--$' > \"$TEMP_OUT\" || true\n")
			f.write("if [ -s \"$TEMP_OUT\" ]; then\n")
			f.write("    cp \"$TEMP_OUT\" \"$RG_OUT\"\n")
			f.write("    seqkit sort -l -r \"$TEMP_OUT\" | head -n 2 > \"$TOP1_OUT\"\n")
			f.write("    rm \"$TEMP_OUT\"\n")
			f.write("else\n")
			f.write("    touch \"$RG_OUT\"\n")
			f.write("    rm -f \"$TEMP_OUT\"\n")
			f.write("fi\n")
		os.chmod(stage1_script, 0o755)
		
		parts_file = os.path.join(output_dir, f"{platform}_parts.txt")
		with open(parts_file, 'w') as f:
			for part in parts:
				f.write(f"{part}\n")
		
		parallel_cmd = f"parallel --will-cite -j {thread_num} bash {stage1_script} :::: {parts_file}"
		start_time = time.time()
		try:
			subprocess.run(parallel_cmd, shell=True, check=True)
		except subprocess.CalledProcessError as e:
			print(f"[{platform.upper()}] Warning: 第一阶段提取出错: {e}")
			return None, 0, 0, 0, 0
		
		stage1_files = glob.glob(f"{stage1_dir}/*.rough.fa")
		valid_stage1_files = [f for f in stage1_files if os.path.getsize(f) > 0]
		print(f"[{platform.upper()}] 粗筛完成: {len(valid_stage1_files)} 个有效文件，耗时 {time.time() - start_time:.2f}秒")
		
		if not valid_stage1_files:
			print(f"[{platform.upper()}] 粗筛无结果")
			return None, 0, 0, 0, 0
		
		# Step 2: 独立频次统计（只统计该平台的 reads）
		print(f"[{platform.upper()}] Step 2: 独立频次统计...")
		kmer_counts = self._count_kmers_in_parts_using_rg(kmer_list_expanded, valid_stage1_files)
		
		# Step 3: 筛选低频 K-mer
		low_freq_kmers = []
		high_freq_kmers = []
		for kmer, count in kmer_counts.items():
			if count <= 100:
				low_freq_kmers.append(kmer)
			else:
				high_freq_kmers.append(kmer)
		
		print(f"[{platform.upper()}] 频次统计: 低频={len(low_freq_kmers)}, 高频={len(high_freq_kmers)}")
		
		if not low_freq_kmers:
			print(f"[{platform.upper()}] Warning: 无低频 K-mer")
		
		# 生成反向互补
		def reverse_complement(seq):
			trans = str.maketrans('ATCGatcg', 'TAGCtagc')
			return seq.translate(trans)[::-1]
		
		low_freq_kmer_file = os.path.join(output_dir, f"{platform}_kmers_low_freq.txt")
		low_freq_with_rc = set()
		for kmer in low_freq_kmers:
			low_freq_with_rc.add(kmer)
			low_freq_with_rc.add(reverse_complement(kmer))
		
		with open(low_freq_kmer_file, 'w') as f:
			for seq in sorted(low_freq_with_rc):
				f.write(f"{seq}\n")
		
		# Step 4: 第二阶段精细筛选
		print(f"[{platform.upper()}] Step 3: 精细筛选...")
		stage2_script = os.path.join(output_dir, f"{platform}_stage2.sh")
		with open(stage2_script, 'w') as f:
			f.write("#!/bin/bash\n")
			f.write("set -e\n")
			f.write("PART_FILE=\"$1\"\n")
			f.write(f"KMER_FILE=\"{low_freq_kmer_file}\"\n")
			f.write(f"OUTPUT_DIR=\"{stage2_dir}\"\n")
			f.write("BASENAME=$(basename \"$PART_FILE\")\n")
			f.write("FINAL_OUT=\"$OUTPUT_DIR/${BASENAME}.final.fa\"\n")
			f.write("if [ ! -s \"$PART_FILE\" ]; then touch \"$FINAL_OUT\"; exit 0; fi\n")
			f.write("rg -f \"$KMER_FILE\" -F -B 1 -N -I \"$PART_FILE\" | grep -v '^--$' > \"$FINAL_OUT\" || true\n")
		os.chmod(stage2_script, 0o755)
		
		stage1_list_file = os.path.join(output_dir, f"{platform}_stage1_files.txt")
		with open(stage1_list_file, 'w') as f:
			for part in valid_stage1_files:
				f.write(f"{part}\n")
		
		parallel_cmd_2 = f"parallel --will-cite -j {thread_num} bash {stage2_script} :::: {stage1_list_file}"
		try:
			subprocess.run(parallel_cmd_2, shell=True, check=True)
		except subprocess.CalledProcessError as e:
			print(f"[{platform.upper()}] Warning: 第二阶段筛选出错: {e}")
		
		# Step 5: 归并结果（简化：直接合并该平台的所有结果）
		print(f"[{platform.upper()}] Step 4: 归并结果...")
		output_file = os.path.join(output_dir, f"{platform}.kmer.Reads.{flag}.fa")
		
		final_files = glob.glob(f"{stage2_dir}/*.final.fa")
		top1_files = glob.glob(f"{stage1_dir}/*.top1.fa")
		
		read_count = 0
		top1_count = 0
		read_ids = set()
		
		with open(output_file, 'w') as out_f:
			# 归并精细筛选结果
			for final_file in final_files:
				if os.path.getsize(final_file) == 0:
					continue
				with open(final_file, 'r') as f:
					for line in f:
						out_f.write(line)
						if line.startswith('>'):
							read_id = line.strip()[1:].split()[0]
							read_ids.add(read_id)
							read_count += 1
			
			# 归并 top1 补充（去重）
			for top1_file in top1_files:
				if os.path.getsize(top1_file) == 0:
					continue
				with open(top1_file, 'r') as f:
					current_lines = []
					current_id = None
					for line in f:
						if line.startswith('>'):
							if current_lines and current_id and current_id not in read_ids:
								out_f.writelines(current_lines)
								read_ids.add(current_id)
								top1_count += 1
							current_id = line.strip()[1:].split()[0]
							current_lines = [line]
						else:
							current_lines.append(line)
					# 处理最后一条
					if current_lines and current_id and current_id not in read_ids:
						out_f.writelines(current_lines)
						read_ids.add(current_id)
						top1_count += 1
		
		print(f"[{platform.upper()}] 完成: {read_count} reads + {top1_count} top1补充")
		
		# 清理临时文件
		try:
			shutil.rmtree(stage1_dir)
			shutil.rmtree(stage2_dir)
			os.remove(stage1_script)
			os.remove(stage2_script)
			os.remove(parts_file)
			os.remove(stage1_list_file)
			os.remove(low_freq_kmer_file)
		except:
			pass
		
		return output_file, read_count, top1_count, len(low_freq_kmers), len(high_freq_kmers)

	def kmerfilter_simplified_parallel(self, kmerseq, flag):
		"""
		简化版并行kmer过滤：HiFi 和 ONT 分别独立执行完整的过滤流程
		
		Parameters:
			kmerseq: 序列
			flag: left 或 right
			
		Returns:
			(hifi_output_file, ont_output_file, log_data)
		"""
		import os
		import subprocess
		import glob
		import time
		from Bio import SeqIO
		
		output_dir = self.roundInput.elongation.roundDir
		
		# Step 0: 读取 HiFi.reads.stat 获取 seedlen
		if self.out:
			base_out_dir = os.path.abspath(self.out)
		else:
			base_out_dir = os.path.dirname(os.path.dirname(output_dir))
		
		stat_file = os.path.join(base_out_dir, "HiFi.reads.stat")
		hifi_seedlen = None
		
		if os.path.exists(stat_file):
			try:
				with open(stat_file, 'r') as f:
					for line in f:
						if line.startswith("seedlen"):
							hifi_seedlen = int(line.strip().split()[1])
							break
				print(f"从 {stat_file} 读取到 HiFi seedlen: {hifi_seedlen} bp")
			except Exception as e:
				print(f"Warning: 无法从 {stat_file} 读取 seedlen: {e}")
		else:
			print(f"Warning: {stat_file} 不存在")
		
		# 如果没有读取到seedlen，使用序列长度
		if hifi_seedlen is None:
			hifi_seedlen = len(kmerseq)
			print(f"使用输入序列长度作为 seedlen: {hifi_seedlen} bp")
		
		# 计算粗筛间隔: min(9*kmer_size, floor(seedlen/kmer_num))
		default_interval = 9 * self.kmer_size
		adaptive_interval = hifi_seedlen // self.kmer_num
		rough_interval = min(default_interval, adaptive_interval)
		
		print(f"\n{'='*80}")
		print(f"独立平台 K-mer 过滤流程（HiFi 和 ONT 分别独立处理）")
		print(f"  - kmer_size: {self.kmer_size}")
		print(f"  - kmer_num: {self.kmer_num}")
		print(f"  - HiFi seedlen: {hifi_seedlen} bp")
		print(f"  - 粗筛间隔: {rough_interval} bp")
		print(f"  - 并行线程数: {self.roundInput.elongation.base.thread}")
		print(f"  - flag: {flag}")
		print(f"{'='*80}\n")
		
		# Step 1: 提取粗筛 K-mer
		print(f"Step 1: 提取粗筛 K-mer（目标数量: {self.kmer_num}，间隔: {rough_interval} bp）...")
		kmer_list = self.extract_kmers_simple(kmerseq, self.kmer_size, self.kmer_num, interval=rough_interval)
		if not kmer_list:
			print("Error: kmer提取失败")
			return None, None, {}
		
		print(f"共提取了 {len(kmer_list)} 个 K-mer 供筛选")
		
		# 生成反向互补序列函数
		def reverse_complement(seq):
			"""生成DNA序列的反向互补"""
			trans = str.maketrans('ATCGatcg', 'TAGCtagc')
			return seq.translate(trans)[::-1]
		
		# 写入kmer到临时文件（包含kmer + RC）
		kmer_file = os.path.join(output_dir, "kmers_initial.txt")
		kmer_with_rc = set()
		for kmer in kmer_list:
			kmer_with_rc.add(kmer)
			kmer_with_rc.add(reverse_complement(kmer))
		
		with open(kmer_file, 'w') as f:
			for kmer in sorted(kmer_with_rc):
				f.write(f"{kmer}\n")
		
		print(f"写入粗筛k-mer文件（包含RC）: {len(kmer_with_rc)} 个序列（{len(kmer_list)} × 2）")
		
		# Step 2: 扩展 K-mer 列表（用于频次统计）
		seq_length = len(kmerseq)
		actual_range = min(hifi_seedlen, seq_length)
		max_kmers = actual_range // self.kmer_size
		
		expanded_kmers = []
		if flag == 'left':
			start_pos = seq_length - self.kmer_size
			for i in range(max_kmers):
				pos = start_pos - (i * self.kmer_size)
				if pos < 0 or start_pos - pos >= actual_range:
					break
				kmer = kmerseq[pos:pos + self.kmer_size].upper()
				expanded_kmers.append(kmer)
		else:
			for i in range(max_kmers):
				pos = i * self.kmer_size
				if pos + self.kmer_size > seq_length or pos >= actual_range:
					break
				kmer = kmerseq[pos:pos + self.kmer_size].upper()
				expanded_kmers.append(kmer)
		
		kmer_list_expanded = sorted(list(set(expanded_kmers)))
		print(f"扩展 K-mer 列表: {len(kmer_list_expanded)} 个唯一kmer")
		
		if len(kmer_list_expanded) == 0:
			print("Error: 扩展后未获取到任何kmer")
			return None, None, {}
		
		# Step 3: 获取reads分片文件列表
		print("\nStep 2: 获取reads分片文件列表...")
		
		hifi_reads_part_dir = os.path.join(base_out_dir, "hifi_reads_part")
		ont_reads_part_dir = os.path.join(base_out_dir, "ont_reads_part")
		
		hifi_parts = glob.glob(f"{hifi_reads_part_dir}/*.fa*") if os.path.exists(hifi_reads_part_dir) else []
		ont_parts = glob.glob(f"{ont_reads_part_dir}/*.fa*") if os.path.exists(ont_reads_part_dir) else []
		
		print(f"找到HiFi分片: {len(hifi_parts)}个")
		print(f"找到ONT分片: {len(ont_parts)}个")
		
		if not hifi_parts and not ont_parts:
			print("Error: 未找到任何reads分片文件")
			return None, None, {}
		
		thread_num = self.roundInput.elongation.base.thread
		
		# Step 4: 分别对 HiFi 和 ONT 执行独立的 K-mer 过滤
		hifi_output = None
		ont_output = None
		hifi_stats = (0, 0, 0, 0)  # (read_count, top1_count, low_freq, high_freq)
		ont_stats = (0, 0, 0, 0)
		
		# 处理 HiFi
		if hifi_parts:
			hifi_output, hifi_read_count, hifi_top1, hifi_low, hifi_high = self._run_kmer_filter_for_platform(
				kmerseq, flag, hifi_parts, 'hifi', output_dir, kmer_file, kmer_list_expanded, thread_num
			)
			hifi_stats = (hifi_read_count, hifi_top1, hifi_low, hifi_high)
		
		# 处理 ONT
		if ont_parts:
			ont_output, ont_read_count, ont_top1, ont_low, ont_high = self._run_kmer_filter_for_platform(
				kmerseq, flag, ont_parts, 'ont', output_dir, kmer_file, kmer_list_expanded, thread_num
			)
			ont_stats = (ont_read_count, ont_top1, ont_low, ont_high)
		
		# 清理公共临时文件
		try:
			os.remove(kmer_file)
		except:
			pass
		
		# 生成日志
		log_data = {
			"K-mer策略": "Independent Platform Filtering (HiFi/ONT separate)",
			"初始提取": len(kmer_list),
			"HiFi低频K-mer": hifi_stats[2],
			"HiFi高频K-mer": hifi_stats[3],
			"HiFi Reads": hifi_stats[0],
			"HiFi Top1补充": hifi_stats[1],
			"ONT低频K-mer": ont_stats[2],
			"ONT高频K-mer": ont_stats[3],
			"ONT Reads": ont_stats[0],
			"ONT Top1补充": ont_stats[1]
		}
		
		self.write_kmer_filtering_log(log_data)
		
		# Memory cleanup
		del kmer_list, kmer_list_expanded, kmer_with_rc, expanded_kmers
		import gc
		gc.collect()
		print(f"\n[kmerfilter] 独立平台过滤完成")
		print(f"  HiFi: {hifi_stats[0]} reads (低频K-mer: {hifi_stats[2]})")
		print(f"  ONT: {ont_stats[0]} reads (低频K-mer: {ont_stats[2]})")
		
		return hifi_output, ont_output, log_data
	
	def kmerfilter(self, inputSeq, kmer_size, kmer_num):
		"""
		使用简化版并行kmer过滤

		Parameters:
			inputSeq: Input sequence file
			kmer_size: Size of k-mer
			kmer_num: Number of k-mers needed

		Returns:
			Filtered reads file path
		"""
		from Bio import SeqIO
		
		print(f"执行简化版并行kmer过滤流程，参数: kmer_size={kmer_size}, kmer_num={kmer_num}")
		
		try:
			# 提取序列
			kmerseq = ""
			for seq_record in SeqIO.parse(inputSeq, "fasta"):
				kmerseq += str(seq_record.seq)
				break
			
			flag = self.roundInput.elongation.base.flag
			
			# 调用简化版并行过滤
			hifi_output, ont_output, log_data = self.kmerfilter_simplified_parallel(kmerseq, flag)
			
			# Determine which output to use based on data_type
			data_type = getattr(self.roundInput.elongation.base, 'data_type', 'hifi')
			
			if data_type == 'ont':
				selected_output = ont_output
				output_type = 'ONT'
			else:
				selected_output = hifi_output
				output_type = 'HiFi'
			
			# Log for debugging
			print(f"K-mer filtering completed for data_type={data_type}")
			print(f"  HiFi output: {hifi_output}")
			print(f"  ONT output: {ont_output}")
			print(f"  Selected output ({output_type}): {selected_output}")
			
			if not selected_output:
				print(f"简化版并行kmer过滤失败: {output_type} output is None")
				return None
			
			print(f"简化版并行kmer过滤完成")
			return selected_output
			
		except Exception as e:
			print(f"kmer过滤过程中发生错误: {e}")
			import traceback
			traceback.print_exc()
			return None

	def minimap2(self):
		# Import required modules
		import os
		import subprocess
		import time
		import glob

		# 根据 data_type 动态选择文件名前缀
		data_type = getattr(self.roundInput.elongation.base, 'data_type', 'hifi')
		if data_type == 'ont':
			file_prefix = 'ont'
		else:
			# HiFi-only 或 Mixed 模式都使用 hifi 前缀（Mixed 模式的 HiFi reads）
			file_prefix = 'hifi'

		alnname=self.roundInput.elongation.roundDir+f"/{file_prefix}.potentialExtensionReads."+self.roundInput.elongation.base.tag+".bam"
		alnname1=self.roundInput.elongation.roundDir+"/extensionReads."+self.roundInput.elongation.base.tag+".fa"

		# If target file already exists, delete it first to avoid appending
		if os.path.exists(alnname):
			try:
				os.remove(alnname)
			except Exception as e:
				print(f"Warning: Unable to delete existing file {alnname}: {e}")

		# Check if k-mer filtering is enabled
		kmer_filter_enabled = getattr(self.roundInput.elongation.base, 'kmer_filter', False)

		if kmer_filter_enabled:
			# K-mer filtering is ENABLED - use single-process minimap2
			print("=" * 80)
			print("K-mer filtering: ENABLED")
			print(f"  - K-mer size: {self.kmer_size}")
			print(f"  - Target k-mer number: {self.kmer_num}")
			print(f"  - Low-frequency threshold: ≤100")
			print(f"  - Expected reads reduction: 50-70%")
			print("  - Minimap2 strategy: Single-process (reads already filtered)")
			print("=" * 80)

			# In mixed mode, use HiFi seed sequence for k-mer filtering (shorter, more efficient)
			data_type = getattr(self.roundInput.elongation.base, 'data_type', 'hifi')
			if data_type == 'mixed' and hasattr(self.roundInput, 'hifiInputSeq'):
				kmer_input_seq = self.roundInput.hifiInputSeq
				print(f"Mixed mode: Using HiFi seed sequence for k-mer filtering: {kmer_input_seq}")
			else:
				kmer_input_seq = self.roundInput.inputSeq
			
			# Use instance variables kmer_size and kmer_num
			filtered_reads = self.kmerfilter(kmer_input_seq, kmer_size=self.kmer_size, kmer_num=self.kmer_num)

			# 检查k-mer过滤结果
			if filtered_reads and os.path.exists(filtered_reads) and os.path.getsize(filtered_reads) > 0:
				reads_to_use = os.path.abspath(filtered_reads)
				print(f"Using filtered reads file: {reads_to_use}, kmer_size={self.kmer_size}, kmer_num={self.kmer_num}")
				# Use single-process minimap2 for filtered reads
				return self._single_process_minimap2(reads_to_use, alnname, alnname1)
			else:
				# K-mer 粗筛没有结果，直接结束，不继续执行无意义的 minimap2
				print(f"K-mer filtering returned no results (all partitions empty)")
				print(f"This indicates no reads contain the seed k-mers, ending extension for this gap")
				return None

		else:
			# K-mer filtering is DISABLED - check if we should use parallel minimap2
			print("=" * 80)
			print("K-mer filtering: DISABLED (using all reads)")
			print("=" * 80)

			# 始终使用单进程 minimap2（benchmark 证明单进程性能更好）
			# 优先使用 processed_reads 中的文件（如果存在），否则使用原始路径
			reads_to_use = self._get_reads_path(file_prefix)

			# Get reads file size for display
			if os.path.exists(reads_to_use):
				reads_size_gb = os.path.getsize(reads_to_use) / (1024**3)
			else:
				reads_size_gb = 0

			print(f"  - Reads file: {reads_to_use}")
			print(f"  - Reads file size: {reads_size_gb:.2f} GB")
			print(f"  - Minimap2 strategy: SINGLE-PROCESS (benchmark proven to be faster)")
			print(f"  - Threads: {self.roundInput.elongation.base.thread}")
			print(f"  - Tip: Add --kmer_filter to enable filtering and reduce processing time")
			print("=" * 80)

			return self._single_process_minimap2(reads_to_use, alnname, alnname1)

	def _get_reads_path(self, file_prefix):
		"""
		获取正确的 reads 文件路径
		优先使用 processed_reads 中的文件（FASTQ 转换后），否则使用原始路径
		
		Args:
			file_prefix: 'hifi' 或 'ont'
			
		Returns:
			Reads 文件的绝对路径
		"""
		import os
		
		# 获取 base output 目录（使用绝对路径）
		base_out_dir = os.path.abspath(self.roundInput.elongation.base.out)
		data_type = getattr(self.roundInput.elongation.base, 'data_type', 'hifi')
		
		# 构建 processed_reads 目录的绝对路径
		processed_reads_dir = os.path.abspath(os.path.join(base_out_dir, "processed_reads"))
		# 如未找到，向上搜索 processed_reads 目录（兼容子任务工作目录）
		if not os.path.exists(processed_reads_dir):
			candidate_bases = [base_out_dir, self.roundInput.elongation.roundDir, os.getcwd()]
			for base in candidate_bases:
				cur = os.path.abspath(base)
				for _ in range(6):
					pr = os.path.join(cur, "processed_reads")
					if os.path.exists(pr):
						processed_reads_dir = pr
						print(f"Located processed_reads directory: {processed_reads_dir}")
						break
					parent = os.path.dirname(cur)
					if parent == cur:
						break
					cur = parent
				else:
					continue
				break
		
		# 根据 file_prefix 确定要查找的文件名模式
		if file_prefix == 'hifi':
			# 首先尝试从 reads_info 获取 working 文件路径（如果有）
			if hasattr(self.roundInput.elongation.base, 'reads_info'):
				reads_info = self.roundInput.elongation.base.reads_info
				if isinstance(reads_info, dict) and 'working_hifi' in reads_info:
					working_hifi_path = reads_info['working_hifi']
					if working_hifi_path and os.path.exists(working_hifi_path):
						print(f"Using working HiFi file from reads_info: {working_hifi_path}")
						return os.path.abspath(working_hifi_path)
			
			# 查找 HiFi processed 文件（后缀可能是 .fa 或 .fasta）
			if os.path.exists(processed_reads_dir):
				import glob
				# 尝试查找 hifi_reads.fa 或 hifi_reads.fasta
				patterns = [
					os.path.join(processed_reads_dir, "hifi_reads.fa"),
					os.path.join(processed_reads_dir, "hifi_reads.fasta")
				]
				for pattern in patterns:
					if os.path.exists(pattern) and os.path.getsize(pattern) > 0:
						print(f"Using processed HiFi file: {pattern}")
						return os.path.abspath(pattern)
				
				# 如果没找到精确匹配，尝试通配符
				hifi_files = glob.glob(os.path.join(processed_reads_dir, "*hifi*.fa")) + \
				             glob.glob(os.path.join(processed_reads_dir, "*hifi*.fasta"))
				if hifi_files:
					print(f"Using processed HiFi file (glob match): {hifi_files[0]}")
					return os.path.abspath(hifi_files[0])
			
			# 没找到 processed 文件，尝试从 reads_info 获取 original 路径
			if hasattr(self.roundInput.elongation.base, 'reads_info'):
				reads_info = self.roundInput.elongation.base.reads_info
				if isinstance(reads_info, dict) and 'original_hifi' in reads_info:
					original_hifi_path = reads_info['original_hifi']
					if isinstance(original_hifi_path, (list, tuple)):
						for p in original_hifi_path:
							if p and os.path.exists(p):
								print(f"Using original HiFi file from reads_info (multi-file first available): {p}")
								return os.path.abspath(p)
					elif original_hifi_path and os.path.exists(original_hifi_path):
						print(f"Using original HiFi file from reads_info: {original_hifi_path}")
						return os.path.abspath(original_hifi_path)
			
			# 最后尝试使用 base.reads 路径（仅当其是FASTA/FASTQ且存在）
			original_path = getattr(self.roundInput.elongation.base, 'reads', None)
			if original_path and os.path.exists(original_path) and os.path.getsize(original_path) > 0 and original_path.lower().endswith((".fa", ".fasta", ".fq", ".fastq")):
				print(f"Processed HiFi file not found, using base.reads: {original_path}")
				return os.path.abspath(original_path)
			else:
				print(f"ERROR: HiFi reads file not found at any location or base.reads is not a FASTA/FASTQ file")
				print(f"  Checked processed_reads_dir: {processed_reads_dir}")
				print(f"  Checked base.reads: {original_path}")
				raise FileNotFoundError(f"HiFi reads file not found or invalid")
			
		elif file_prefix == 'ont':
			# 首先尝试从 reads_info 获取 working 文件路径（如果有）
			if hasattr(self.roundInput.elongation.base, 'reads_info'):
				reads_info = self.roundInput.elongation.base.reads_info
				if isinstance(reads_info, dict) and 'working_ont' in reads_info:
					working_ont_path = reads_info['working_ont']
					if working_ont_path and os.path.exists(working_ont_path):
						print(f"Using working ONT file from reads_info: {working_ont_path}")
						return os.path.abspath(working_ont_path)
			
			# 查找 ONT processed 文件
			if os.path.exists(processed_reads_dir):
				import glob
				# 尝试查找 ont_reads.fa 或 ont_reads.fasta
				patterns = [
					os.path.join(processed_reads_dir, "ont_reads.fa"),
					os.path.join(processed_reads_dir, "ont_reads.fasta")
				]
				for pattern in patterns:
					if os.path.exists(pattern) and os.path.getsize(pattern) > 0:
						print(f"Using processed ONT file: {pattern}")
						return os.path.abspath(pattern)
				
				# 如果没找到精确匹配，尝试通配符
				ont_files = glob.glob(os.path.join(processed_reads_dir, "*ont*.fa")) + \
				            glob.glob(os.path.join(processed_reads_dir, "*ont*.fasta"))
				if ont_files:
					print(f"Using processed ONT file (glob match): {ont_files[0]}")
					return os.path.abspath(ont_files[0])
			
			# 没找到 processed 文件，尝试从 reads_info 获取 original 路径
			if hasattr(self.roundInput.elongation.base, 'reads_info'):
				reads_info = self.roundInput.elongation.base.reads_info
				if isinstance(reads_info, dict) and 'original_ont' in reads_info:
					original_ont_path = reads_info['original_ont']
					if isinstance(original_ont_path, (list, tuple)):
						for p in original_ont_path:
							if p and os.path.exists(p):
								print(f"Using original ONT file from reads_info (multi-file first available): {p}")
								return os.path.abspath(p)
					elif original_ont_path and os.path.exists(original_ont_path):
						print(f"Using original ONT file from reads_info: {original_ont_path}")
						return os.path.abspath(original_ont_path)
			
			# 最后尝试使用 base.ont_reads（仅当其是FASTA/FASTQ且存在）
			if hasattr(self.roundInput.elongation.base, 'ont_reads') and self.roundInput.elongation.base.ont_reads:
				original_path = self.roundInput.elongation.base.ont_reads
				if original_path and os.path.exists(original_path) and os.path.getsize(original_path) > 0 and original_path.lower().endswith((".fa", ".fasta", ".fq", ".fastq")):
					print(f"Processed ONT file not found, using base.ont_reads: {original_path}")
					return os.path.abspath(original_path)
				else:
					print(f"ERROR: ONT reads file not found at any location or base.ont_reads is not a FASTA/FASTQ file")
					print(f"  Checked processed_reads_dir: {processed_reads_dir}")
					print(f"  Checked base.ont_reads: {original_path}")
					raise FileNotFoundError(f"ONT reads file not found or invalid")
			else:
				print(f"ERROR: ONT reads attribute not found in base object")
				raise AttributeError("ont_reads attribute not found in base object")
		else:
			raise ValueError(f"Invalid file_prefix: {file_prefix}")

	def _single_process_minimap2(self, reads_to_use, alnname, alnname1):
		"""
		Single-process minimap2 alignment (original strategy)

		Args:
			reads_to_use: Path to reads file
			alnname: Output BAM file path
			alnname1: Extension reads FASTA file path

		Returns:
			Tuple of (alnname, commandline, returncode)
		"""
		import os
		import time

		# Get data type
		data_type = getattr(self.roundInput.elongation.base, 'data_type', 'hifi')

		# In mixed mode, choose correct input sequence based on reads type
		if data_type == 'mixed':
			# Determine reads type by checking reads path
			reads_basename = os.path.basename(reads_to_use)
			if 'hifi' in reads_basename.lower():
				# HiFi reads - use HiFi input sequence
				input_seq = self.roundInput.hifiInputSeq
				preset = 'asm20'
				print(f"Mixed mode: Using HiFi input sequence for HiFi reads")
			elif 'ont' in reads_basename.lower():
				# ONT reads - use ONT input sequence
				input_seq = self.roundInput.ontInputSeq
				preset = 'map-ont'
				print(f"Mixed mode: Using ONT input sequence for ONT reads")
			else:
				# Fallback: use primary inputSeq
				input_seq = self.roundInput.inputSeq
				preset = 'asm20'
				print(f"Warning: Mixed mode but cannot determine reads type from filename, using default input sequence")
		else:
			# Single data type mode - use primary inputSeq
			input_seq = self.roundInput.inputSeq
			# Choose minimap2 preset by data type: ONT-only uses map-ont; others use asm20
			preset = 'map-ont' if data_type == 'ont' else 'asm20'

		# Ensure inputSeq uses absolute path
		input_seq_abs = os.path.abspath(input_seq)
		print(f"minimap2 using absolute paths: input_seq={input_seq_abs}, reads={reads_to_use}")

		commandline = f"minimap2 -t {self.roundInput.elongation.base.thread} -Y -ax {preset} {input_seq_abs} {reads_to_use} | samtools view -bS >{alnname}"

		# If file already exists and is valid, return directly
		if os.path.exists(alnname)==True and os.path.getsize(alnname)!=0 and os.path.exists(alnname1)==True and os.path.getsize(alnname1)!=0:
			return alnname,commandline,str(0)
		else:
			# Use os.system() like v1 - no timeout limit (matches v1 behavior)
			print(f"Executing command: {commandline}")
			start_time = time.time()

			output = os.system(commandline)
			minimaptag = 1

			# Retry up to 3 times if failed (matches v1 behavior)
			if output != 0:
				while output != 0:
					print(f"minimap2 command execution failed, return code: {output}")
					print(f"Retry {minimaptag} of minimap2 command...")
					output = os.system(commandline)
					minimaptag += 1
					if minimaptag >= 3:
						print("minimap2 cannot do proper alignment!!!")
						sys.exit(1)

			# Check output file size (no indexing to match v1 behavior)
			if os.path.exists(alnname):
				file_size = os.path.getsize(alnname)
				if file_size == 0:
					print(f"Warning: minimap2 generated BAM file size is 0 bytes")
				else:
					print(f"minimap2 generated BAM file size: {file_size} bytes")

			elapsed_time = time.time() - start_time
			print(f"Single-process minimap2 completed in {elapsed_time:.2f} seconds")
			return alnname, commandline, str(output)

	def readlog(self):
		logfilet=open(self.log,'r')
		for row in logfilet:
			row1=row.rstrip().split('\t')
			if row1[0]=='potentialExtensionReadsAln':
				self.potentialExtensionReadsAln=row1[1]
			elif row1[0]=='minimap2Command':
				self.minimap2Command=row1[1]
			elif row1[0]=='minimap2Output':
				self.minimap2Output=row1[1]
			elif row1[0]=='minimumThresholdReadsAln':
				self.minimumThresholdReadsAln=row1[1]
			elif row1[0]=='minimumThresholdReadsID':
				self.minimumThresholdReadsID=row1[1].split(';')
			elif row1[0]=='minimumThresholdExtensionReadsAln':
				self.minimumThresholdExtensionReadsAln=row1[1]
			elif row1[0]=='minimumThresholdExtensionReads':
				self.minimumThresholdExtensionReads=row1[1]
			elif row1[0]=='minimumThresholdExtensionReadsID':
				self.minimumThresholdExtensionReadsID=row1[1].split(';')
			elif row1[0]=='selectPotentialExtensionReadsAln':
				self.selectPotentialExtensionReadsAln=row1[1]

			elif row1[0]=='selectPotentialExtensionReadsID':
				if row1[1]!='None':
					self.selectPotentialExtensionReadsID=row1[1].split(';')
				else:
					self.selectPotentialExtensionReadsID=[]
			elif row1[0]=='selectReadsNum':
				self.selectReadsNum=int(row1[1])
			elif row1[0]=='extensionReadsAln':
				self.extensionReadsAln=row1[1]
			elif row1[0]=='extensionReads':
				self.extensionReads=row1[1]
			elif row1[0]=='extensionReadsID':
				if row1[1]!='None':
					self.extensionReadsID=row1[1].split(';')
				else:
					self.extensionReadsID=[]
			elif row1[0]=='extensionReadsNum':
				self.extensionReadsNum=int(row1[1])
			elif row1[0]=='selectMappingQuality':
				self.selectMappingQuality=int(row1[1])
			elif row1[0]=='selectAlignmentLength':
				self.selectAlignmentLength=int(row1[1])
			elif row1[0]=='selectNMAlignmentLengthratio':
				self.selectNMAlignmentLengthratio=float(row1[1])
			elif row1[0]=='readsExtensionLength':
				self.readsExtensionLength=int(row1[1])
			elif row1[0]=='extensionReadsEdge':
				self.extensionReadsEdge=int(row1[1])
			elif row1[0]=='note':
				if len(row1)==1:
					self.note=''
				else:
					self.note=row1[1]
		logfilet.close()

	def cleanup_memory(self):
		"""Clean up memory by clearing large data structures"""
		import gc
		
		# Clear large lists
		for attr in ['minimumThresholdReadsID', 'minimumThresholdExtensionReadsID',
		             'selectPotentialExtensionReadsID', 'extensionReadsID',
		             'potentialExtensionReadsID', 'selectExtensionReadsID',
		             'potentialExtensionReadsAln', 'selectPotentialExtensionReadsAln',
		             'extensionReadsAln', 'kmerFilteredReadsID', 'lastRoundUsedReads', 'usedReads']:
			if hasattr(self, attr):
				if isinstance(getattr(self, attr), list):
					setattr(self, attr, [])
		
		# Clear dictionaries
		for attr in ['readsDict', 'kmerCountDict']:
			if hasattr(self, attr):
				setattr(self, attr, {})
		
		# Clear roundInput reference
		if hasattr(self, 'roundInput'):
			self.roundInput = None
		
		gc.collect()
