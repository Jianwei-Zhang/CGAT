import re
import Bio
import os
import sys
import re
import getopt
import pysam
from pysam import AlignmentFile
import Bio
from Bio import SeqIO
import tempfile
import subprocess
import shutil
import FindExtensionReads
from FindExtensionReads import FindExtensionReads
import FindExtensionContigs
from FindExtensionContigs import FindExtensionContigs

class InputSequence(object):
	def __init__(self,Elongation):
		self.elongation=Elongation

		base = self.elongation.base
		# Generic fallback seed length (set by GapFiller based on statistics)
		base_seed_len = getattr(base, 'seedLen', None)

		def _resolve_seed_len(explicit_len, label):
			"""Resolve per-type seed length, falling back to base.seedLen if needed.

			This prevents cases where, e.g., ONT-only mode has ontSeedLen=None but
			seedLen is properly set from statistics. In that case we still want to
			proceed using the generic seedLen rather than failing.
			"""
			if explicit_len is not None:
				return explicit_len
			if base_seed_len is not None:
				print(f"[InputSequence] {label} seed length not set explicitly, "
				      f"falling back to base.seedLen={base_seed_len}")
				return base_seed_len
			raise ValueError(f"{label} seed length is None. This indicates a parameter passing issue.")

		# Generate separate seed sequence files based on data type
		if base.data_type == 'hifi':
			# HiFi only mode
			self.inputSeq = self.elongation.roundDir + "/hifi.inputCutSequence.fasta"
			hifi_seed_len = _resolve_seed_len(getattr(base, 'hifiSeedLen', None), "HiFi")
			self._generateSeedSequence(self.inputSeq, hifi_seed_len, "HiFi")

		elif base.data_type == 'ont':
			# ONT only mode
			self.inputSeq = self.elongation.roundDir + "/ont.inputCutSequence.fasta"
			ont_seed_len = _resolve_seed_len(getattr(base, 'ontSeedLen', None), "ONT")
			self._generateSeedSequence(self.inputSeq, ont_seed_len, "ONT")

		elif base.data_type == 'mixed':
			# Mixed mode - generate both files
			self.hifiInputSeq = self.elongation.roundDir + "/hifi.inputCutSequence.fasta"
			self.ontInputSeq = self.elongation.roundDir + "/ont.inputCutSequence.fasta"

			hifi_seed_len = _resolve_seed_len(getattr(base, 'hifiSeedLen', None), "HiFi")
			ont_seed_len = _resolve_seed_len(getattr(base, 'ontSeedLen', None), "ONT")

			self._generateSeedSequence(self.hifiInputSeq, hifi_seed_len, "HiFi")
			self._generateSeedSequence(self.ontInputSeq, ont_seed_len, "ONT")

			# Set primary inputSeq for backward compatibility (use ONT for k-mer extraction as per your requirement)
			self.inputSeq = self.ontInputSeq
		else:
			# Fallback to original behavior
			self.inputSeq = self.elongation.roundDir + "/inputCutSequence.fasta"
			default_seed_len = _resolve_seed_len(base_seed_len, "Default")
			self._generateSeedSequence(self.inputSeq, default_seed_len, "Default")

		# Set inputSeedSequence from primary inputSeq
		for gseq in SeqIO.parse(self.inputSeq,'fasta'):
			self.inputSeedSequence=gseq
			break

	def _generateSeedSequence(self, output_file, seed_length, data_type_name):
		"""Generate seed sequence file with specified length"""
		print(f"Generating {data_type_name} seed sequence file: {output_file} with length: {seed_length}")

		if seed_length is None:
			raise ValueError(f"{data_type_name} seed length is None. This indicates a parameter passing issue.")

		with open(output_file, 'w') as filet:
			for gseq in SeqIO.parse(self.elongation.roundInputSeq, 'fasta'):
				length = int(seed_length)
				if len(gseq.seq) <= length:
					# If sequence length is less than or equal to seedLen, use entire sequence
					l = '>' + gseq.id + "_all\n" + str(gseq.seq) + "\n"
					print(f"Sequence {gseq.id} length ({len(gseq.seq)}bp) is less than or equal to {data_type_name} seed length ({length}bp), using entire sequence as seed.")
				else:
					# Otherwise extract sequence of specified length according to flag
					if self.elongation.base.flag == 'left':
						l = '>' + gseq.id + "_" + str(length) + "\n" + str(gseq.seq[-length:]) + "\n"
					else:
						l = '>' + gseq.id + "_" + str(length) + "\n" + str(gseq.seq[:length]) + "\n"
				filet.write(l)

def mummer(seq1,seq2,name):
	mr=name

	# Check if input files exist
	if not os.path.exists(seq1):
		print(f"Error: Input sequence file 1 does not exist: {seq1}")
		# Create empty output file to avoid downstream errors
		empty_output = mr+".delta.filter.coords"
		with open(empty_output, 'w') as f:
			pass
		return empty_output

	if not os.path.exists(seq2):
		print(f"Error: Input sequence file 2 does not exist: {seq2}")
		# Create empty output file to avoid downstream errors
		empty_output = mr+".delta.filter.coords"
		with open(empty_output, 'w') as f:
			pass
		return empty_output

	try:
		commendline="nucmer -c 90 -l 40 -p "+mr+" "+seq1+" "+seq2
		result = os.system(commendline)
		if result != 0:
			print(f"Warning: nucmer command failed with exit code {result}")

		commendline="delta-filter -m "+mr+".delta > "+mr+".delta.filter"
		result = os.system(commendline)
		if result != 0:
			print(f"Warning: delta-filter command failed with exit code {result}")

		commendline="show-coords -TrHcl "+mr+".delta.filter > "+mr+".delta.filter.coords"
		result = os.system(commendline)
		if result != 0:
			print(f"Warning: show-coords command failed with exit code {result}")

	except Exception as e:
		print(f"Error during mummer analysis: {e}")
		# Create empty output file to avoid downstream errors
		empty_output = mr+".delta.filter.coords"
		with open(empty_output, 'w') as f:
			pass
		return empty_output

	mr=mr+".delta.filter.coords"
	return mr

class OutputSequence(object):
	def __init__(self,ExtensionContigs,Elongation):
		self.extensionContigs=ExtensionContigs
		self.Elongation=Elongation
		self.outputLog=self.Elongation.roundDir+"/outputExtensionSequence.log"
		self.outputSequence=self.Elongation.roundDir+"/outputExtensionSequence.fasta"
		if os.path.exists(self.outputSequence)==True and os.path.getsize(self.outputSequence)!=0:
                        self.readlog()
		else:
			logfile=open(self.outputLog,'w')
			self.totalOutputSequenceLength=self.extensionSequence()
			logLine="outputSequence\t"+self.outputSequence+"\n"
			logLine+="totalOutputSequenceLength\t"+str(self.totalOutputSequenceLength)+"\n"
			# Record the seedlen used in this round for next round's reference
			logLine+="usedSeedLen\t"+str(self.used_seedlen)+"\n"
			if self.Elongation.base.data_type == 'mixed':
				logLine+="dataType\tmixed\n"
				logLine+="hifiSeedLen\t"+str(self.Elongation.base.hifiSeedLen)+"\n"
				logLine+="ontSeedLen\t"+str(self.Elongation.base.ontSeedLen)+"\n"
			self.ExtensionUsedReads=self.checkExtensionReads()
			logLine+="ExtensionUsedReads\t"+";".join(self.ExtensionUsedReads)+"\n"
			self.linkedSequence,self.linkedSequenceNote,self.linkedSequenceAln=self.linkgap()
			logLine+="linkedSequence\t"+self.linkedSequence+"\n"
			for i in self.linkedSequenceNote.rstrip().split('\n'):
				logLine+="linkedSequenceNote\t"+i+"\n"
			logLine+="linkedSequenceAln\t"+self.linkedSequenceAln+"\n"
			logfile.writelines(logLine)
			logfile.close()
	def readlog(self):
		logfile=open(self.outputLog,'r')
		self.linkedSequenceNote=''
		# Initialize used_seedlen (for backward compatibility with old logs)
		self.used_seedlen = None
		for row in logfile:
			row1=row.rstrip().split('\t')
			if row1[0]=='outputSequence':
				self.outputSequence=row1[1]
			elif row1[0]=="totalOutputSequenceLength":
				self.totalOutputSequenceLength=int(row1[1])
			elif row1[0]=="usedSeedLen":
				# Read the seedlen that was used in this round
				self.used_seedlen=int(row1[1])
			elif row1[0]=="ExtensionUsedReads":
				self.ExtensionUsedReads=row1[1].split(';')
			elif row1[0]=="linkedSequenceNote":
				self.linkedSequenceNote=self.linkedSequenceNote+"\t".join(row1[1:])
			elif row1[0]=='linkedSequence':
				self.linkedSequence=row1[1]
			elif row1[0]=="linkedSequenceAln":
				self.linkedSequenceAln="\t".join(row1[1:])
		logfile.close()
	
	def linkgap(self):
		mummern=self.Elongation.roundDir+"/extensionSequence.linkgap.aln."+self.Elongation.base.tag+".mummer"
		mummerout=mummern+".delta.filter.coords"
		
		flag=self.Elongation.base.flag
		edg=self.Elongation.base.edge
		tail_length = edg + 20000  # 截取长度：edge + 20000
		
		# 记录原始序列长度，用于坐标转换
		output_orig_len = 0
		terminal_orig_len = 0
		output_offset = 0  # outputSequence 坐标偏移量
		terminal_offset = 0  # terminalSeq 坐标偏移量
		
		if os.path.exists(mummerout)!=True:
			# ===== 截取序列以加速比对 =====
			# 1. 获取原始序列长度
			for gseq in SeqIO.parse(self.outputSequence, 'fasta'):
				output_orig_len = len(gseq.seq)
				break
			for gseq in SeqIO.parse(self.Elongation.base.terminalSeq, 'fasta'):
				terminal_orig_len = len(gseq.seq)
				break
			
			# 2. 截取 outputSequence
			output_tail_file = self.Elongation.roundDir + "/outputExtensionSequence.tail.fasta"
			with open(output_tail_file, 'w') as f:
				for gseq in SeqIO.parse(self.outputSequence, 'fasta'):
					if len(gseq.seq) > tail_length:
						if flag == 'left':
							# 截取右端
							tail_seq = gseq.seq[-tail_length:]
							output_offset = len(gseq.seq) - tail_length
						else:
							# 截取左端
							tail_seq = gseq.seq[:tail_length]
							output_offset = 0
					else:
						tail_seq = gseq.seq
						output_offset = 0
					f.write(f">{gseq.id}\n{tail_seq}\n")
			
			# 3. 截取 terminalSeq
			terminal_tail_file = self.Elongation.roundDir + "/terminalSeq.tail.fasta"
			with open(terminal_tail_file, 'w') as f:
				for gseq in SeqIO.parse(self.Elongation.base.terminalSeq, 'fasta'):
					if len(gseq.seq) > tail_length:
						if flag == 'left':
							# 截取左端
							tail_seq = gseq.seq[:tail_length]
							terminal_offset = 0
						else:
							# 截取右端
							tail_seq = gseq.seq[-tail_length:]
							terminal_offset = len(gseq.seq) - tail_length
					else:
						tail_seq = gseq.seq
						terminal_offset = 0
					f.write(f">{gseq.id}\n{tail_seq}\n")
			
			# 4. 用截取后的序列进行比对
			mummerout=mummer(terminal_tail_file, output_tail_file, mummern)
			
			# 5. 保存偏移量信息到文件，供后续使用
			offset_file = self.Elongation.roundDir + "/linkgap_offset.info"
			with open(offset_file, 'w') as f:
				f.write(f"output_offset\t{output_offset}\n")
				f.write(f"terminal_offset\t{terminal_offset}\n")
				f.write(f"output_orig_len\t{output_orig_len}\n")
				f.write(f"terminal_orig_len\t{terminal_orig_len}\n")
		else:
			# 从文件读取偏移量信息
			offset_file = self.Elongation.roundDir + "/linkgap_offset.info"
			if os.path.exists(offset_file):
				with open(offset_file, 'r') as f:
					for line in f:
						parts = line.strip().split('\t')
						if parts[0] == 'output_offset':
							output_offset = int(parts[1])
						elif parts[0] == 'terminal_offset':
							terminal_offset = int(parts[1])
						elif parts[0] == 'output_orig_len':
							output_orig_len = int(parts[1])
						elif parts[0] == 'terminal_orig_len':
							terminal_orig_len = int(parts[1])
		
		n1=self.Elongation.roundDir+"/linkedSequence.fasta"
		note=''
		f1=open(mummerout,'r')
		lout1=[]
		for row in f1:
			row1=row.rstrip().split('\t')
			len1=int(row1[4])
			if len1>=10000:
				lout1.append(row)

		f1.close()

		lout2=[]
		for row in lout1:
			row1=row.rstrip().split('\t')
			# 截取序列的坐标
			a_tail,b_tail,c_tail,d_tail=int(row1[0]),int(row1[1]),int(row1[2]),int(row1[3])
			# 转换为原始序列坐标
			a = a_tail + terminal_offset
			b = b_tail + terminal_offset
			c = c_tail + output_offset
			d = d_tail + output_offset
			ctgmame=row1[-1]
			if flag=='left':
				# 使用原始序列长度进行判断
				if d >= output_orig_len - edg and a <= edg:
					lout2.append((row, a, b, c, d))
			else:
				if b >= terminal_orig_len - edg and c <= edg:
					lout2.append((row, a, b, c, d))
				
		lout=''
		lout_coords = None
		idty=0
		for item in lout2:
			row, a, b, c, d = item
			row1=row.rstrip().split('\t')
			e=float(row1[6])
			if lout=='':
				lout=row
				lout_coords = (a, b, c, d)
				idty=e
			else:
				if e>idty:
					idty=e
					lout=row
					lout_coords = (a, b, c, d)
		
		if lout!='':
			note=note+'ExtensionSequence can close the GAP!\n'
			self.Elongation.endSignal=True
			row1=lout.rstrip().split('\t')
			# 使用转换后的原始坐标
			a, b, c, d = lout_coords
			for gseq in SeqIO.parse(self.outputSequence,'fasta'):
				Seq2=gseq.seq
			for gseq in SeqIO.parse(self.Elongation.base.terminalSeq,'fasta'):
				if gseq.id==row1[-2]:
					Seq1=gseq.seq
			for gseq in SeqIO.parse(self.Elongation.base.initialSeq,'fasta'):
				Seq0=gseq.seq
			
			# 构建转换后坐标的比对行，用于返回值（供可视化模块使用）
			# row1格式: a, b, c, d, len1, len2, identity, seq1_len, seq2_len, cov1, cov2, seq1_name, seq2_name
			row1_converted = row1.copy()
			row1_converted[0] = str(a)  # terminal start
			row1_converted[1] = str(b)  # terminal end
			row1_converted[2] = str(c)  # output start
			row1_converted[3] = str(d)  # output end
			row1_converted[7] = str(terminal_orig_len)  # terminal 原始总长度
			row1_converted[8] = str(output_orig_len)    # output 原始总长度
			lout_converted = '\t'.join(row1_converted)
			
			if flag!='left':
				seqfin=Seq1[:b]+Seq2[d:]
				note=note+'\tGAP Length: '+str(self.Elongation.extensionLen+self.extensionContigs.extensionLength-int(row1[5]))+"\n\tLinked Sequence Length: "+str(len(seqfin))+"\n"
				l='>ExtensionSequence'+"\tgap:"+str(self.Elongation.extensionLen+self.extensionContigs.extensionLength-int(row1[5]))+"\tlen:"+str(len(seqfin))+"\tRound:round"+self.Elongation.roundDir.split('round')[-1]+"\tAln:"+';'.join(row1_converted)+"\n"+str(seqfin)+"\n"
			else:
				seqfin=Seq2+Seq1[b:]
				note=note+'\tGAP Length: '+str(self.Elongation.extensionLen+self.extensionContigs.extensionLength-int(row1[5]))+"\n\tLinked Sequence Length: "+str(len(seqfin))+"\n"
				l='>ExtensionSequence'+"\tgap:"+str(self.Elongation.extensionLen+self.extensionContigs.extensionLength-int(row1[5]))+"\tlen:"+str(len(seqfin))+"\tRound:round"+self.Elongation.roundDir.split('round')[-1]+"\tAln:"+';'.join(row1_converted)+"\n"+str(seqfin)+"\n"
			ft=open(n1,'w')
			ft.writelines(l)
			ft.close()
			return n1,note,lout_converted
		return n1,note,lout

	def checkExtensionReads(self):
		IDlist=self.extensionContigs.extensionContigID
		readslist=[]
		for i in IDlist:
			if i in self.extensionContigs.hifiasmResultDict:
				readslist=readslist+self.extensionContigs.hifiasmResultDict[i]
			else:
				readslist.append(i)
		return readslist

	def extensionSequence(self):
		ft=open(self.outputSequence,'w')

		# 混合模式下使用HiFi的seedlen（因为hifiasm以HiFi为主输入）
		if self.Elongation.base.data_type == 'mixed':
			seedlen = int(self.Elongation.base.hifiSeedLen)
			print(f"Mixed mode: Using HiFi seed length {seedlen} bp for sequence merging")
			print(f"  (hifiasm uses HiFi as primary input)")
		else:
			# 单一模式使用原有逻辑
			seedlen = int(self.Elongation.base.seedLen)
		
		# 记录使用的 seedlen 到属性，供其他方法使用和记录到log
		self.used_seedlen = seedlen

		i=0
		if 'No extension contigs or reads found' not in self.extensionContigs.selectContigNote:
			for gseq in SeqIO.parse(self.extensionContigs.extensionSequence,'fasta'):
				for gseq1 in SeqIO.parse(self.Elongation.roundInputSeq,'fasta'):
					if self.Elongation.base.flag=='left':
						Seq1=gseq1.seq[:-seedlen]
						seq2=gseq1.seq[:-seedlen]+gseq1.seq[-seedlen:]
						if not gseq1.seq==seq2:
							print (gseq1.seq==seq2)
							print ('wrong link')
							sys.exit()
						Seq2=Seq1+gseq.seq
						l='>'+gseq.id+'\n'+str(Seq2)+"\n"
						ft.writelines(l)
					else:
						Seq1=gseq1.seq[seedlen:]
						seq2=gseq1.seq[:seedlen]+gseq1.seq[seedlen:]
						if not gseq1.seq==seq2:
							print (gseq1.seq==seq2)
							print ('wrong link')
							sys.exit()
						Seq2=gseq.seq+Seq1
						l='>'+gseq.id+'\n'+str(Seq2)+"\n"
						ft.writelines(l)
						i+=1
			if i>=2:
				for gseq in SeqIO.parse(self.extensionContigs.extensionSequence,'fasta'):
					for gseq1 in SeqIO.parse(self.Elongation.roundInputSeq,'fasta'):
						print (gseq.id,gseq1.id)
				sys.exit()
			ft.close()
		else:
			for gseq1 in SeqIO.parse(self.Elongation.roundInputSeq,'fasta'):
				l='>'+gseq1.id+'\n'+str(gseq1.seq)+"\n"
				Seq2=gseq1.seq
				ft.writelines(l)
		ft.close()
		return len(Seq2)



class GapFillerClass(object):
	def __init__(self, Elongation, out=None):
		self.usedReads=Elongation.usedReads
		self.lastRoundUsedReads=Elongation.lastRoundUsedReads
		self.Elongation=Elongation
		self.roundInput=InputSequence(self.Elongation)


		
		# Get output directory parameter
		if out is not None:
			# If out parameter is directly passed, use it with priority
			out_dir = out
		else:
			# Try to get from object attributes
			out_dir = None
			if hasattr(self.Elongation.base, "out"):
				out_dir = self.Elongation.base.out
			elif hasattr(self.Elongation, "parameter") and len(self.Elongation.parameter) > 4:
				out_dir = self.Elongation.parameter[4]
		
		# Create output directory (if it doesn't exist)
		output_dir = self.roundInput.elongation.roundDir
		if not os.path.exists(output_dir):
			os.makedirs(output_dir)

		# Initialize roundOutput attribute to None to prevent AttributeError when other code tries to access this attribute
		self.roundOutput = None

		# Pass out parameter to FindExtensionReads, with optimized k-mer parameters
		self.ExtensionReads=FindExtensionReads(
			self.roundInput,
			self.lastRoundUsedReads,
			self.usedReads,
			self.Elongation.base.kmer_size,
			self.Elongation.base.kmer_num,
			out=out_dir
		)
		
		# Check if extension reads were found successfully
		# In mixed mode, continue if at least one platform succeeded
		mixed_mode_status = getattr(self.ExtensionReads, 'mixed_mode_status', None)
		should_continue = (self.ExtensionReads.note == '' or 
		                   mixed_mode_status in ['both_success', 'hifi_only', 'ont_only'])
		if should_continue:
			# Extension reads found, proceed with normal assembly
			print("Extension reads found successfully, proceeding with assembly...")
			# Get data_type and ont_reads from Elongation.base if available
			data_type = getattr(self.Elongation.base, 'data_type', 'hifi')
			ont_reads = getattr(self.Elongation.base, 'ont_reads', None)

			# Get original FASTQ paths for hifiasm (if available)
			original_reads_info = getattr(self.Elongation.base, 'original_reads_info', None)

			self.ExtensionContigs=FindExtensionContigs(self.ExtensionReads, data_type, ont_reads, original_reads_info)
			if 'No extension contigs or reads found' not in self.ExtensionContigs.selectContigNote and "Reach the maximum Length" not in self.ExtensionContigs.selectContigNote:
				self.roundOutput=OutputSequence(self.ExtensionContigs,self.Elongation)
		else:
			# No extension reads found - this is a normal condition, not an error
			print(f"No extension reads found (note: {self.ExtensionReads.note}). This is normal for some gaps.")
			print("Ending extension loop - no need to execute FindExtensionContigs.")

			# Create a mock ExtensionContigs object to maintain compatibility
			class MockExtensionContigs:
				def __init__(self):
					self.selectContigNote = "No extension contigs or reads found"
					self.extensionLength = 0
					self.extensionContigs = None
					self.selectExtensionContigsAln = []
					self.selectContigIdentity = 0
					self.selectContigAlnLength = 0
					self.extensionSeqNote = "No extension reads found, skipped contig assembly"

			self.ExtensionContigs = MockExtensionContigs()

			# Set end signal to terminate extension loop
			self.Elongation.endSignal = True
			print("Extension loop termination signal set.")

			# No roundOutput needed since we're ending the loop
			self.roundOutput = None



	def cleanup_memory(self):
		"""Clean up memory by clearing large data structures"""
		import gc
		
		# Clear ExtensionReads
		if hasattr(self, 'ExtensionReads') and self.ExtensionReads is not None:
			er = self.ExtensionReads
			for attr in ['minimumThresholdReadsID', 'minimumThresholdExtensionReadsID',
			             'selectPotentialExtensionReadsID', 'extensionReadsID',
			             'potentialExtensionReadsID', 'selectExtensionReadsID',
			             'potentialExtensionReadsAln', 'selectPotentialExtensionReadsAln',
			             'extensionReadsAln', 'kmerFilteredReadsID']:
				if hasattr(er, attr):
					setattr(er, attr, [])
			for attr in ['readsDict', 'kmerCountDict']:
				if hasattr(er, attr):
					setattr(er, attr, {})
			if hasattr(er, 'roundInput'):
				er.roundInput = None
			self.ExtensionReads = None
		
		# Clear ExtensionContigs
		if hasattr(self, 'ExtensionContigs') and self.ExtensionContigs is not None:
			ec = self.ExtensionContigs
			for attr in ['hifiasmResultDict', 'contigDict', 'readsDict']:
				if hasattr(ec, attr):
					setattr(ec, attr, {})
			for attr in ['selectExtensionContigsAln', 'extensionContigID', 'contigAlnList']:
				if hasattr(ec, attr):
					setattr(ec, attr, [])
			if hasattr(ec, 'extensionSequence'):
				ec.extensionSequence = None
			self.ExtensionContigs = None
		
		# Clear roundInput
		if hasattr(self, 'roundInput') and self.roundInput is not None:
			if hasattr(self.roundInput, 'inputSeedSequence'):
				self.roundInput.inputSeedSequence = None
			if hasattr(self.roundInput, 'elongation'):
				self.roundInput.elongation = None
			self.roundInput = None
		
		# Clear roundOutput
		if hasattr(self, 'roundOutput') and self.roundOutput is not None:
			ro = self.roundOutput
			for attr in ['ExtensionUsedReads']:
				if hasattr(ro, attr):
					setattr(ro, attr, [])
			if hasattr(ro, 'extensionContigs'):
				ro.extensionContigs = None
			if hasattr(ro, 'Elongation'):
				ro.Elongation = None
			self.roundOutput = None
		
		# Clear other references
		self.Elongation = None
		self.usedReads = []
		self.lastRoundUsedReads = []
		
		gc.collect()

	@staticmethod
	def _reverse_complement(seq):
		trans = str.maketrans("ACGTNacgtn", "TGCANtgcan")
		return seq.translate(trans)[::-1]

	@classmethod
	def _canonical_kmer(cls, seq):
		seq_u = seq.upper()
		rc = cls._reverse_complement(seq_u)
		return seq_u if seq_u <= rc else rc
