import re
import os
import sys
import getopt
import pysam
from pysam import AlignmentFile
import Bio
from Bio import SeqIO
import GapFiller
from GapFiller import GapFiller
import N50Check
from N50Check import N50Check
import subprocess
import json
from pathlib import Path

class CtgLinker(object):
	def __init__(self,parameterlist, kparameters):
		# Handle both old and new parameter formats
		print(f"CtgLinker received parameter list with {len(parameterlist)} parameters")

		if len(parameterlist) >= 21:
			# New format with dual seed lengths and ONT readsDict:
			# [mode, remove, thread, reads, out, genomeSeq, edge, filterDepthHifi, filterDepthOnt,
			#  MaximumExtensionLength, MaximumExtensionRound, data_type, ont_reads, readsDict,
			#  maxReadsLen, hifiSeedLen, ontSeedLen, original_reads_info, ont_readsDict]
			self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepthHifi,self.filterDepthOnt,self.MaximunExtensionLength,self.MaximumExtensionRound,self.data_type,self.ont_reads,self.readsDict,self.maxReadsLen,self.hifiSeedLen=parameterlist[:16]
			self.ontSeedLen = parameterlist[16] if len(parameterlist) > 16 else None
			self.original_reads_info = parameterlist[17] if len(parameterlist) > 17 else None
			self.ont_readsDict = parameterlist[18] if len(parameterlist) > 18 else None
			# For backward compatibility, set seedLen to hifiSeedLen
			self.seedLen = self.hifiSeedLen
			self.filterDepth = self.filterDepthHifi  # For backward compatibility

		elif len(parameterlist) >= 19:
			# Format with dual seed lengths but no ONT readsDict:
			# [mode, remove, thread, reads, out, genomeSeq, edge, filterDepthHifi, filterDepthOnt,
			#  MaximumExtensionLength, MaximumExtensionRound, data_type, ont_reads, readsDict,
			#  maxReadsLen, hifiSeedLen, ontSeedLen, original_reads_info]
			self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepthHifi,self.filterDepthOnt,self.MaximunExtensionLength,self.MaximumExtensionRound,self.data_type,self.ont_reads,self.readsDict,self.maxReadsLen,self.hifiSeedLen=parameterlist[:16]
			self.ontSeedLen = parameterlist[16] if len(parameterlist) > 16 else None
			self.original_reads_info = parameterlist[17] if len(parameterlist) > 17 else None
			self.ont_readsDict = None
			# For backward compatibility, set seedLen to hifiSeedLen
			self.seedLen = self.hifiSeedLen
			self.filterDepth = self.filterDepthHifi  # For backward compatibility

		elif len(parameterlist) >= 16:
			# Old format with single seedLen:
			# [mode, remove, thread, reads, out, genomeSeq, edge, filterDepthHifi, filterDepthOnt,
			#  MaximumExtensionLength, MaximumExtensionRound, data_type, ont_reads, readsDict,
			#  maxReadsLen, seedLen]
			self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepthHifi,self.filterDepthOnt,self.MaximunExtensionLength,self.MaximumExtensionRound,self.data_type,self.ont_reads,self.readsDict,self.maxReadsLen,self.seedLen=parameterlist[:16]
			# For backward compatibility, set dual seed lengths to same value
			self.hifiSeedLen = self.seedLen
			self.ontSeedLen = self.seedLen
			self.original_reads_info = None
			self.ont_readsDict = None
			self.filterDepth = self.filterDepthHifi  # For backward compatibility

		elif len(parameterlist) == 15:
			# Previous format without MaximumExtensionRound:
			# [mode, remove, thread, reads, out, genomeSeq, edge, filterDepthHifi, filterDepthOnt,
			#  MaximumExtensionLength, data_type, ont_reads, readsDict, maxReadsLen, seedLen]
			self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepthHifi,self.filterDepthOnt,self.MaximunExtensionLength,self.data_type,self.ont_reads,self.readsDict,self.maxReadsLen,self.seedLen=parameterlist[:15]
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			# For backward compatibility, set dual seed lengths to same value
			self.hifiSeedLen = self.seedLen
			self.ontSeedLen = self.seedLen
			self.original_reads_info = None
			self.ont_readsDict = None
			self.filterDepth = self.filterDepthHifi  # For backward compatibility

		elif len(parameterlist) == 12:
			# Old format:
			# [mode, remove, thread, reads, out, genomeSeq, edge, filterDepth,
			#  MaximumExtensionLength, readsDict, maxReadsLen, seedLen]
			self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepth,self.MaximunExtensionLength,self.readsDict,self.maxReadsLen,self.seedLen=parameterlist
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			self.filterDepthHifi = self.filterDepth  # Map old filterDepth to filterDepthHifi
			self.filterDepthOnt = None
			self.data_type = 'hifi'
			self.ont_reads = None
			# For backward compatibility, set dual seed lengths to same value
			self.hifiSeedLen = self.seedLen
			self.ontSeedLen = self.seedLen
			self.original_reads_info = None
			self.ont_readsDict = None
		else:
			raise ValueError(f"Unsupported parameter list length for CtgLinker: {len(parameterlist)}. Expected 12, 15, 16, 19, or 21+ parameters.")
		# Unpack kparameters - contains kmer_size, kmer_num, and kmer_filter
		if len(kparameters) == 3:
			# Standard format: [kmer_size, kmer_num, kmer_filter]
			self.kmer_size, self.kmer_num, self.kmer_filter = kparameters
		elif len(kparameters) == 2:
			# Legacy format: [kmer_size, kmer_num] (kmer_filter defaults to False)
			self.kmer_size, self.kmer_num = kparameters
			self.kmer_filter = False
		else:
			raise ValueError(f"Unsupported kparameters length: {len(kparameters)}. Expected 2 or 3 parameters.")

		# Print seed length information for debugging
		print(f"CtgLinker initialized with:")
		print(f"  data_type: {self.data_type}")
		print(f"  hifiSeedLen: {self.hifiSeedLen}")
		print(f"  ontSeedLen: {self.ontSeedLen}")
		print(f"  seedLen (primary): {self.seedLen}")
		print(f"  ont_readsDict: {'Available' if self.ont_readsDict is not None else 'None'}")

		self.ctgSeq=self.out+"/Genome.inputCtg.fa"
		self.ctgSeqLog=self.out+"/Genome.inputCtg.log"
		if os.path.exists(self.ctgSeqLog)!=True or os.path.getsize(self.ctgSeqLog)==0:
			# 统一使用hifiSeedLen过滤contigs
			# mixed模式也用hifiSeedLen，保持edge library构建的一致性
			if self.data_type == 'ont':
				filter_seedlen = self.ontSeedLen if self.ontSeedLen else self.hifiSeedLen
			else:  # hifi or mixed
				filter_seedlen = self.hifiSeedLen
			N50Check([self.genomeSeq, filter_seedlen, self.ctgSeq, self.ctgSeqLog])
		self.projectSeq=self.out+"/DG.project.fa"
		file1= open(self.projectSeq, 'w').close()

		self.project=self.out+"/project"
		if not os.path.exists(self.project):
			os.makedirs(self.project)

		self.unplaced=self.out+"/unplaced.txt"
		file1=open(self.unplaced,'w')
		i=0
		for gseq in SeqIO.parse(self.ctgSeq,'fasta'):
			l=gseq.description+"\n"
			file1.writelines(l)	
			i+=1
		self.unplacednum=i
		file1.close()

		self.used=self.out+"/used.txt"
		file1=open(self.used,'w')
		l='# "" (empty) means sequences still can elongate\n# "**" means sequences can no longer elongate\n#DG\tright-end\tleft-end\ttags\n'
		file1.writelines(l)
		file1.close()

		self.agppwd=self.out+"/DG.agp.path.txt"
		file1=open(self.agppwd,'w').close()

		self.agp=self.out+"/DG.scaffold.agp"
		file1=open(self.agp,'w').close()

		self.scaffoldSeq=self.out+"/DG.scaffold.fa"
		file1=open(self.scaffoldSeq,'w').close()

		# 记录已被连接的 scaffold（不应再出现在 edge library 中）
		self.usedScaffolds=self.out+"/used.scaffolds.txt"
		file1=open(self.usedScaffolds,'w')
		l='# Scaffolds that have been linked to other DGs\n# These scaffolds should not appear in edge library\n'
		file1.writelines(l)
		file1.close()

		self.CtgLinkerPipline()
		self.scaffoldSeqLog=self.out+"/DG.scaffold.log"
		N50Check([self.scaffoldSeq,self.scaffoldSeqLog])

	def CtgLinkerPipline(self):
		self.scaffoldID=1
		self.projectID=1
		self.Lastround=False
		while self.unplacednum >0 or self.Lastround==False:
			self.roundInit()
			if os.path.exists(self.projectfasta)==True and os.path.getsize(self.projectfasta)!=0:
				self.skipRound()
			else:
				self.elongationDG()
			self.projectID+=1
			self.removeFileCtg()
			
			# Memory cleanup between DGs to prevent memory accumulation
			self._cleanup_between_dgs()

	def removeFileCtg(self):
		if self.unplacednum >0:
			if self.remove==1 or self.remove==2:
				if os.path.exists(self.projectData):
					commondline="rm -rf "+self.projectData
					os.system(commondline)
		else:
			if self.remove==1:
				if os.path.exists(self.project):
					# Modified: Don't delete entire output directory immediately, keep final result files
					# Save important files list
					important_files = [
						self.out+"/DG.scaffold.fa",  # Final result sequence
						self.out+"/DG.scaffold.log", # Final result log
						self.out+"/DG.scaffold.agp", # Final result AGP file
						self.out+"/DG.project.fa"    # Project sequence file
					]

					# Check if final result files have been generated
					if all(os.path.exists(f) for f in important_files):
						print("Keeping final result files, cleaning intermediate process files...")

						# Only delete intermediate process files, keep final results
						for root, dirs, files in os.walk(self.project):
							for file in files:
								file_path = os.path.join(root, file)
								os.remove(file_path)

						print("Cleaned intermediate process files, kept final results and directory structure")
					else:
						print("Warning: Final result files not all generated yet, skipping output directory cleanup")
						# Don't execute deletion

	def skipRound(self):
		logFile=open(self.projectlog,'r')
		for row in logFile:
			if row[0]!='#':
				row1=row.rstrip().split('\t')
				if row1!=[]:
					if row1[0]=='projectID':
						self.projectID=int(row1[1])
					elif row1[0]=='projectOut':
						self.projectOut=row1[1]
					elif row1[0]=='projectData':
						self.projectData=row1[1]
					elif row1[0]=='projectfasta':
						self.projectfasta=row1[1]
						for gseq in SeqIO.parse(self.projectfasta,'fasta'):
							seqout=gseq.seq
					elif row1[0]=='projectagppwd':
						self.projectagppwd=row1[1]
					elif row1[0]=='projectTerminalCtg':
						self.projectagppwd=row1[1]
					elif row1[0]=='TerminalCtgID':
						if len(row1)!=1:
							self.TerminalCtgID=row1[1].split(";")
						else:
							self.TerminalCtgID==[]
					elif row1[0]=='projectused':
						self.projectused=row1[1]
					elif row1[0]=='ctgUsedID':
						if len(row1)==1:
							self.ctgUsedID=[]
						else:
							self.ctgUsedID=row1[1].split(";")
					elif row1[0]=='flaglist':
						self.flaglist=row1[1].split(";")
					elif row1[0]=='roundInputSeqFile':
						self.roundInputSeqFile=row1[1]
					elif row1[0]=='roundInputSeqID':
						self.roundInputSeqID=row1[1]
					elif row1[0]=='roundInputSeqLength':
						self.roundInputSeqLength=int(row1[1])
					elif row1[0]=='placedlist':
						self.placedlist=row1[1].split(";")
					elif row1[0]=='projectagp':
						if len(row1)<=2:
							self.projectagp=row1[1]
					elif row1[0]=='DGUsedCtgList':
						if len(row1)==1:
							self.DGUsedCtgList=[]
						else:
							self.DGUsedCtgList=row1[1].split(";")
					elif row1[0]=='projectusedLine':
						self.projectusedLine='\t'.join(row1[1:])+"\n"
					elif row1[0]=='projectSeq':
						self.projectSeq=row1[1]
					elif row1[0]=='leftTag':
						if len(row1)==1:
							self.leftTag=''
						else:
							self.leftTag=row1[1]
					elif row1[0]=='rightTag':
						if len(row1)==1:
							self.rightTag=''
						else:
							self.rightTag=row1[1]
					elif row1[0]=='unplacedlist':
						if len(row1)==1:
							self.unplacedlist=[]
						else:
							self.unplacedlist=row1[1].split(";")
					elif row1[0]=='unplacednum':
						self.unplacednum=int(row1[1])
		logFile.close()
		DGusetaglist=self.DGUsedCtgList

		file1=open(self.used,'r')
		file2=open(self.projectOut+'/temp','w')
		for row in file1:
			if row[0]!='#':
				row1=row.split('\t')
				if row1[0] in DGusetaglist:
					# ✨✨✨ 修复：被吸收的 DG 应该标记为 **/**（完全不可用）✨✨✨
					l=row1[0]+"\t**\t**\t"+row1[-1]
					file2.writelines(l)
				else:
					file2.writelines(row)
			else:
				file2.writelines(row)
		file1.close()

		file1=open(self.agppwd,'a')
		l="DG"+str(self.projectID)+"\t"+self.projectagp+"\n"
		file1.writelines(l)
		file1.close()

		if self.rightTag=='**' and self.leftTag=='**':
			self.setScaffold(seqout)
			self.scaffoldID+=1
			self.Lastround=True
		else:
			self.Lastround=False
		file2.writelines(self.projectusedLine)
		file2.close()
		file1=open(self.projectSeq,'a')
		for gseq in SeqIO.parse(self.projectfasta,'fasta'):
			l='>'+gseq.description+"\n"+str(gseq.seq)+"\n"
			file1.writelines(l)
		file1.close()
		commondline='mv '+self.projectOut+'/temp '+self.used
		os.system(commondline)

		file1=open(self.unplaced,'r')
		file2=open(self.projectOut+'/temp','w')
		unplacedn=0
		self.unplacedlist=[]
		for row in file1:
			if row.rstrip() not in self.placedlist:
				file2.writelines(row)
				unplacedn+=1
				self.unplacedlist.append(row.rstrip())
		file1.close()
		file2.close()
		commondline='mv '+self.projectOut+'/temp '+self.unplaced
		os.system(commondline)
		self.unplacednum=unplacedn

	def elongationDG(self):
		logFile=open(self.projectlog,'w')
		LogLine="\n\n*****************\n\nprojectID\t"+str(self.projectID)+"\n"
		LogLine+="projectOut\t"+str(self.projectOut)+"\n"
		LogLine+="projectData\t"+str(self.projectData)+"\n"
		LogLine+="projectfasta\t"+str(self.projectfasta)+"\n"
		LogLine+="projectagppwd\t"+str(self.projectagppwd)+"\n"
		print (LogLine)
		logline=self.elongationDGInit()
		LogLine+=logline
		
		# 检查是否需要跳过当前 DG（两端都已完成）
		if hasattr(self, 'skipCurrentDG') and self.skipCurrentDG:
			self.skipCurrentDG = False  # 重置标志
			print(f"[CtgLinker] Skipping DG{self.projectID} - both directions already completed")
			logFile.writelines(LogLine)
			logFile.close()
			return
		
		self.setGapFiller()

		logline=self.elongationDGNext()
		LogLine+=logline
		print (LogLine)
		logFile.writelines(LogLine)
		logFile.close()

	def elongationDGNext(self):
		file1=open(self.projectagp,'w')
		ltused=[]
		ltunplaced=[]
		logline='projectagp\t'+self.projectagp+"\n"
		
		# 防御性检查：outdict 为空时直接返回
		if len(self.outdict) == 0:
			print("[CtgLinker] Warning: outdict is empty, skipping elongationDGNext")
			file1.close()
			return logline
		
		if len(self.outdict)==1:
			for k,v in self.outdict.items():
				filet=open(v.agp,'r')
				rownum=0
				if k=='left':
					s2=-1
					e2=-1
					stag=''
				else:
					s1=-1
					e1=-1
					etag=''
				InitialSeq = None
				for gseq in SeqIO.parse(v.initialSeq,'fasta'):
					InitialSeq=gseq
				if InitialSeq is None:
					print(f"Warning: No sequence found in {v.initialSeq}, skipping...")
					filet.close()
					continue
				for agpl in filet:
					rownum+=1
					agpl1=agpl.split('\t')
					if 'Right' not in agpl1[5] and 'Left' not in agpl1[5]:
						lt="DG"+str(self.projectID)+"\t"+"\t".join(agpl1[1:])
						ltused.append(agpl1[5])
						ltunplaced.append(agpl1[5])
					else:
						lt="DG"+str(self.projectID)+"\t"+"\t".join(agpl1[1:5])+"\t"+"DG"+str(self.projectID)+"-"+"\t".join(agpl1[5:])
						nametemp=agpl1[5].split("DG"+str(self.projectID))[-1]
						ltused.append(InitialSeq.id+nametemp)
					if k=='left' and InitialSeq.id in agpl:
						s2=int(agpl1[1])-1
						e2=int(agpl1[2])
					if k=='right' and InitialSeq.id in agpl:
						s1=int(agpl1[1])-1
						e1=int(agpl1[2])
					file1.writelines(lt)
					logline=logline+'projectagp\t'+lt
					print (agpl,InitialSeq.id,k=='Left',k, InitialSeq.id in agpl)
			file1.close()
			# 初始化为空字符串，表示可以继续延伸
			etag=''
			stag=''
			GF=v
			for gseq in SeqIO.parse(GF.Elongation.finalSeq,'fasta'):
				GFseq=gseq
				seqoutt=str(gseq.seq)
		else:
			sGF=self.outdict['left']
			eGF=self.outdict['right']
			for gseq in SeqIO.parse(sGF.Elongation.finalSeq,'fasta'):
				sGFseq=gseq
			for gseq in SeqIO.parse(eGF.Elongation.finalSeq,'fasta'):
				eGFseq=gseq
			j=1
			file2=open(eGF.agp,'r')
			s1=-1
			e1=-1
			rownum=0
			lt1=[]
			InitialSeq = None
			# Check if initialSeq file exists before trying to parse it
			if not os.path.exists(eGF.initialSeq):
				print(f"Warning: {eGF.initialSeq} not found (may have been deleted), skipping initial sequence parsing...")
				file2.close()
			else:
				for gseq in SeqIO.parse(eGF.initialSeq,'fasta'):
					InitialSeq=gseq
			if InitialSeq is None:
				print(f"Warning: No sequence found in {eGF.initialSeq}, skipping...")
				if not file2.closed:
					file2.close()
			else:
				for agpl in file2:
					rownum+=1
					agpl1=agpl.split('\t')
					if 'Right' not in agpl1[5]:
						if InitialSeq.id in agpl:
							lt1=agpl1
							endlen1=int(agpl1[6])-1
						else:
							lt="DG"+str(self.projectID)+"\t"+"\t".join(agpl1[1:])
							logline=logline+'projectagp\t'+lt
							file1.writelines(lt)
							j+=1
						ltused.append(agpl1[5])
						ltunplaced.append(agpl1[5])
					else:
						lt="DG"+str(self.projectID)+"\t"+"\t".join(agpl1[1:5])+"\t"+"DG"+str(self.projectID)+"-"+"\t".join(agpl1[5:])
						nametemp=agpl1[5].split("DG"+str(self.projectID))[-1]
						ltused.append(InitialSeq.id+nametemp)
						file1.writelines(lt)
						j+=1
						logline=logline+'projectagp\t'+lt
					if InitialSeq.id in agpl:
						s1=int(agpl1[1])-1
						e1=int(agpl1[2])
			file2.close()
			stag=''
			
			file2=open(sGF.agp,'r')
			if s1==-1:
				endlen=0
			else:
				if endlen1!=0:
					endlen=len(eGFseq.seq[:s1])-endlen1
				else:
					endlen=len(eGFseq.seq[:s1])
			s2=-1
			e2=-1
			rownum=0
			InitialSeq = None
			for gseq in SeqIO.parse(eGF.initialSeq,'fasta'):
				InitialSeq=gseq
			if InitialSeq is None:
				print(f"Warning: No sequence found in {eGF.initialSeq}, skipping...")
				file2.close()
			else:
				for agpl in file2:
					rownum+=1
					agpl1=agpl.split('\t')
					if InitialSeq.id in agpl:
						s2=int(agpl1[1])-1
						e2=int(agpl1[2])
						if lt1!=[]:
							a=int(lt1[7])-int(agpl1[7])
						else:
							a=0
						if s1==-1 and e1==-1:
							lt="DG"+str(self.projectID)+"\t"+str(int(agpl1[1])+endlen-a)+"\t"+str(int(agpl1[2])+endlen-a)+"\t"+str(j)+"\t"+"\t".join(agpl1[4:])
							if 'Left' not in agpl1[5]:
								ltunplaced.append(agpl1[5])
							ltused.append(agpl1[5])
						else:
							lt="DG"+str(self.projectID)+"\t"+lt1[1]+"\t"+str(int(lt1[2])-a)+"\t"+str(j)+"\tw\t"+lt1[5]+"\t"+lt1[6]+"\t"+str(int(lt1[7])-a)+"\t"+lt1[8]
						file1.writelines(lt)
						logline=logline+'projectagp\t'+lt
						j+=1
					else:
						if 'Left' not in agpl1[5]:
							lt="DG"+str(self.projectID)+"\t"+str(int(agpl1[1])+endlen)+"\t"+str(int(agpl1[2])+endlen)+"\t"+str(j)+"\t"+"\t".join(agpl1[4:])
							ltused.append(agpl1[5])
							ltunplaced.append(agpl1[5])
						else:
							lt="DG"+str(self.projectID)+"\t"+str(int(agpl1[1])+endlen)+"\t"+str(int(agpl1[2])+endlen)+"\t"+str(j)+"\t"+agpl1[4]+"\tDG"+str(self.projectID)+"-"+"\t".join(agpl1[5:])
							nametemp=agpl1[5].split("DG"+str(self.projectID))[-1]
							ltused.append(InitialSeq.id+nametemp)
						file1.writelines(lt)
						logline=logline+'projectagp\t'+lt
						j+=1
			file2.close()
			file1.close()
			etag=''

		file1=open(self.used,'r')
		file2=open(self.projectOut+'/temp','w')

		if len(ltused)!=0:
			# ✨✨✨ 修复：直接从process.log读取最终结果，更可靠！✨✨✨
			# 通过检查每个方向的process.log中的"Final ExtensionSequence"来判断状态
			
			def check_direction_status_from_log(gf_object, direction_name):
				"""
				从GapFiller对象的process.log中读取最终结果
				返回: '**' 如果失败或连接到scaffold, '' 如果成功连接到contig
				"""
				try:
					# 构建process.log路径
					process_log = os.path.join(gf_object.out, 'process.log')
					
					if os.path.exists(process_log):
						with open(process_log, 'r') as f:
							content = f.read()
							# 查找"Final ExtensionSequence:"行
							for line in content.split('\n'):
								if line.startswith('Final ExtensionSequence:'):
									final_result = line.split(':', 1)[1].strip()
									print (f"[CtgLinker] {direction_name} final result: {final_result}")
									
									# 检查是否包含失败标记
									if 'noExtensionContigsorReads' in final_result or \
									   'noNewExtensionReads' in final_result or \
									   'reachMaximumLength' in final_result:
										return '**'
									
									# 检查是否连接到scaffold
									# scaffold的edge格式: "DG1-scaffold-edge-right" 或 "DG1-scaffold-edge-left"
									if '-scaffold-edge-' in final_result:
										# 连接到scaffold，该方向应标记为'**'
										# 因为scaffold两端都是'**'，合并后该端也应该是'**'
										print(f"[CtgLinker] {direction_name} linked to scaffold, marking as '**'")
										return '**'
									
									# 成功连接到普通contig
									return ''
					
					# 如果没有找到process.log，回退到旧逻辑
					print (f"[CtgLinker] Warning: {process_log} not found, using fallback logic")
					return None
				except Exception as e:
					print (f"[CtgLinker] Error reading process.log for {direction_name}: {e}")
					return None
			
			# 初始化状态为None（表示尚未确定）
			stag = None
			etag = None
			
			# 尝试从process.log读取状态
			if len(self.outdict) == 1:
				# 单方向延伸
				for k, v in self.outdict.items():
					if k == 'right':
						result = check_direction_status_from_log(v, 'Right')
						if result is not None:
							stag = result
							etag = '**'  # 另一端没有延伸
						break
					elif k == 'left':
						result = check_direction_status_from_log(v, 'Left')
						if result is not None:
							etag = result
							stag = '**'  # 另一端没有延伸
						break
			else:
				# 双方向延伸
				if 'right' in self.outdict:
					result = check_direction_status_from_log(self.outdict['right'], 'Right')
					if result is not None:
						stag = result
				if 'left' in self.outdict:
					result = check_direction_status_from_log(self.outdict['left'], 'Left')
					if result is not None:
						etag = result
			
			# ✨ 回退逻辑：如果process.log读取失败（None），使用原有的ltused检查
			# 这部分保留旧逻辑作为fallback
			if stag is None or etag is None:
				print (f"[CtgLinker] Using fallback ltused check (stag={stag}, etag={etag})")
				
				# 只对None的方向使用fallback
				if stag is None:
					# 初始状态：根据原有逻辑设置
					if 'noExtensionContigsorReads' in ltused[0] or \
					   'noNewExtensionReads' in ltused[0] or \
					   'reachMaximumLength' in ltused[0]:
						stag='**'
					else:
						stag=''
					
					# 遍历所有元素，检查包含Right标记的失败情况
					for element in ltused:
						if 'Right' in element:
							if 'noExtensionContigsorReads' in element or \
							   'noNewExtensionReads' in element or \
							   'reachMaximumLength' in element:
								stag='**'
								print (f"[CtgLinker] Right direction failed: {element}")
								break
				
				if etag is None:
					if 'noExtensionContigsorReads' in ltused[-1] or \
					   'noNewExtensionReads' in ltused[-1] or \
					   'reachMaximumLength' in ltused[-1]:
						etag='**'
					else:
						etag=''
					
					# 遍历所有元素，检查包含Left标记的失败情况
					for element in ltused:
						if 'Left' in element:
							if 'noExtensionContigsorReads' in element or \
							   'noNewExtensionReads' in element or \
							   'reachMaximumLength' in element:
								etag='**'
								print (f"[CtgLinker] Left direction failed: {element}")
								break
		
		if len(self.outdict)!=1:
			if s1==-1 and e1==-1:
				stag='**'
			if s2==-1 and e2==-1:
				etag='**'
		else:
			if 'right' in self.outdict:
				print (s1,e1)
				if s1==-1 and e1==-1:
					stag='**'
				etag='**'
			if 'left' in self.outdict:
				print (s2,e2)
				if s2==-1 and e2==-1:
					etag='**'
				stag='**'
		print (stag,etag,"1,stag,etag!!!!!\n")
		self.placedlist=ltunplaced
		logline=logline+"placedlist\t"+";".join(ltunplaced)+"\n"
		DGusetaglist=[]
		for row in file1:
			print (row)
			row1=row.split('\t')
			# 检查 DG ID 是否在 ltused 中（支持前缀匹配，如 DG1 匹配 DG1-Right-xxx）
			dg_id_in_ltused = row1[0] in ltused or any(item.startswith(row1[0] + '-') or item.startswith(row1[0] + '\t') for item in ltused)
			if dg_id_in_ltused:
				stt=row1[1]
				ett=row1[2]
				if stt=='**':
					stag='**'
				if ett=='**':
					etag='**'
				DGn=row1[0]
				DGusetaglist.append(DGn)
				setDGusetaglist=sorted(list(set(DGusetaglist)))
				while DGn!='':
					file3=open(self.used,'r')
					for r3 in file3:
						r31=r3.rstrip().split('\t')
						if r31[0]==DGn:
							DGn1=DGn
							DGn=''
							r32=r31[3].split(';')
							for dgn in r32:
								print (dgn,'DG' in dgn,r31[0] not in dgn,r31[0])
								if 'DG' in dgn and r31[0] not in dgn:
									DGn=dgn
									if DGn not in DGusetaglist:
										DGusetaglist.append(DGn)
					file3.close()
					if sorted(list(set(DGusetaglist)))==setDGusetaglist:
						DGn=''
					else:
						print (DGusetaglist)
						setDGusetaglist=sorted(list(set(DGusetaglist)))
		print (stag,etag,"2,stag,etag!!!!!\n")
		self.DGUsedCtgList=DGusetaglist
		logline=logline+"DGUsedCtgList\t"+";".join(self.DGUsedCtgList)+"\n"
		file1.close()
		file1=open(self.used,'r')
		file2=open(self.projectOut+'/temp','w')
		for row in file1:
			row1=row.split('\t')
			if row1[0] in DGusetaglist:
				# ✨✨✨ 修复：被吸收的 DG 应该标记为 **/**（完全不可用）✨✨✨
				# 而不是继承当前 DG 的状态，否则会导致被吸收的 DG 被再次选为 seed
				l=row1[0]+"\t**\t**\t"+row1[-1]
				file2.writelines(l)
			else:
				file2.writelines(row)
		file1.close()
		print (stag,etag,"3,stag,etag!!!!!\n")
		
		# ✨✨✨ 修复：将 ctgUsedID 中的 contigs 也添加到 ltused ✨✨✨
		# ctgUsedID 包含了 direct connection 检测到的 contigs
		# 这些 contigs 可能没有出现在 AGP 文件中，但应该被记录为已使用
		for ctg_id in self.ctgUsedID:
			# 只添加原始 contigs（排除 DG 和 seed 本身）
			if ctg_id not in ltused and not ctg_id.startswith('DG'):
				# 检查是否是当前 seed
				if hasattr(self, 'roundInputSeq') and ctg_id != self.roundInputSeq.id:
					ltused.append(ctg_id)
					print(f"[CtgLinker] Adding ctgUsedID to ltused: {ctg_id}")
		
		ltusedl="DG"+str(self.projectID)+"\t"+stag+"\t"+etag+"\t"+";".join(ltused)+"\n"
		logline=logline+'projectusedLine\t'+ltusedl+"\n"
		self.projectusedLine=ltusedl
		file3=open(self.projectused,'w')
		file2.writelines(ltusedl)
		file3.writelines(ltusedl)
		file2.close()
		file3.close()
		
		commondline='mv '+self.projectOut+'/temp '+self.used
		os.system(commondline)
		
		file1=open(self.projectSeq,'a')
		
		# 判断是否保留延伸序列
		def should_keep_extension(ltused_item):
			"""判断是否应该保留延伸序列（只有成功连接才保留）"""
			# 检查是否有失败标记
			if 'noExtensionContigsorReads' in ltused_item or \
			   'noNewExtensionReads' in ltused_item or \
			   'reachMaximumLength' in ltused_item:
				return False  # 失败或未连接，不保留
			return True  # 成功连接，保留
		
		if len(self.outdict)==1:
			# 单方向延伸
			ChrID=self.roundInputSeq.description.split('\t')[-1]
			
			# 判断是否保留延伸序列
			if ltused and should_keep_extension(ltused[0]):
				seqoutt=GFseq.seq  # 保留延伸序列
			else:
				# 不保留延伸，使用原始 roundInputSeq
				for gseq in SeqIO.parse(self.roundInputSeqFile, 'fasta'):
					seqoutt=gseq.seq
					break
			
			l=">DG"+str(self.projectID)+"\t"+";".join(ltused)+"\t"+ChrID+"\n"+seqoutt+"\n"
		else:
			# ========== 简化的双方向合并逻辑 ==========
			# Left结果:  [TargetContig_L]---[延伸]---[Seed完整]
			# Right结果:                   [Seed完整]---[延伸]---[TargetContig_R]
			# 最终:      [TargetContig_L]---[延伸]---[Seed]---[延伸]---[TargetContig_R]
			#                              ↑                 ↑
			#                        Left[:-seedLen]    +   Right
			
			ChrID=self.roundInputSeq.description.split('\t')[-1]
			seed_len = self.roundInputSeqLength
			
			# 获取 Left 序列（优先使用 direct.final.fa）
			left_direct = os.path.join(sGF.out, f"{sGF.name}.direct.final.fa")
			if os.path.exists(left_direct) and os.path.getsize(left_direct) > 0:
				for gseq in SeqIO.parse(left_direct, 'fasta'):
					left_seq = str(gseq.seq)
					break
			else:
				left_seq = str(sGFseq.seq)
			
			# 获取 Right 序列（优先使用 direct.final.fa）
			right_direct = os.path.join(eGF.out, f"{eGF.name}.direct.final.fa")
			if os.path.exists(right_direct) and os.path.getsize(right_direct) > 0:
				for gseq in SeqIO.parse(right_direct, 'fasta'):
					right_seq = str(gseq.seq)
					break
			else:
				right_seq = str(eGFseq.seq)
			
			# 判断 Left 是否有效
			keep_left = ltused and should_keep_extension(ltused[-1])
			# 判断 Right 是否有效
			keep_right = ltused and should_keep_extension(ltused[0])
			
			if not keep_left and not keep_right:
				# 两端都失败，使用原始 seed
				for gseq in SeqIO.parse(self.roundInputSeqFile, 'fasta'):
					seqoutt=gseq.seq
					break
			elif not keep_left and keep_right:
				# 只有 Right 成功：直接用 Right（已包含完整 Seed）
				seqoutt = right_seq
			elif keep_left and not keep_right:
				# 只有 Left 成功：Left[:-seed_len] + 原始 Seed
				for gseq in SeqIO.parse(self.roundInputSeqFile, 'fasta'):
					seed_seq = str(gseq.seq)
					break
				seqoutt = left_seq[:-seed_len] + seed_seq
			else:
				# 两端都成功：Left[:-seed_len] + Right
				seqoutt = left_seq[:-seed_len] + right_seq
			
			l=">DG"+str(self.projectID)+"\t"+";".join(ltused)+"\t"+ChrID+"\n"+str(seqoutt)+"\n"
		logline=logline+'projectSeq\t'+self.projectSeq+"\n"
		file1.writelines(l)
		file1.close()
		file3=open(self.projectfasta,'w')
		file3.writelines(l)
		file3.close()

		file1=open(self.agppwd,'a')
		l="DG"+str(self.projectID)+"\t"+self.projectagp+"\n"
		file1.writelines(l)
		file1.close()
		file3=open(self.projectagppwd,'w')
		file3.writelines(l)
		file3.close()
		self.leftTag=etag
		self.rightTag=stag
		logline=logline+'leftTag\t'+self.leftTag+"\n"
		logline=logline+'rightTag\t'+self.rightTag+"\n"
		if stag=='**' and etag=='**':
			self.setScaffold(seqoutt)  # Now seqoutt is always defined
			self.scaffoldID+=1
			self.Lastround=True
		else:
			self.Lastround=False

		file1=open(self.unplaced,'r')
		file2=open(self.projectOut+'/temp','w')
		unplacedn=0
		self.unplacedlist=[]
		
		for row in file1:
			row1=row.rstrip().split('\t')
			if row1[0] not in ltunplaced:
				file2.writelines(row)
				unplacedn+=1
				self.unplacedlist.append(row.rstrip())
		file1.close()
		file2.close()
		logline=logline+"unplacedlist\t"+";".join(self.unplacedlist)+"\n"
		print ("unplacedlist\t"+";".join(self.unplacedlist)+"\n")
		commondline='mv '+self.projectOut+'/temp '+self.unplaced
		os.system(commondline)
		self.unplacednum=unplacedn
		logline=logline+"unplacednum\t"+str(self.unplacednum)+"\n"
		return logline

	def _create_reads_symlinks(self, target_dir):
		"""
		Create symlinks to preprocessed reads files in the subtask directory.
		Similar to TelSeekerPart2._link_reads_data()

		Args:
			target_dir: The subtask directory (e.g., DG1-Left, DG1-Right)
		"""
		print(f"\n[CtgLinker] Creating symlinks to preprocessed files in {os.path.basename(target_dir)}")
		print(f"  Source directory: {self.out}")
		print(f"  Data type: {self.data_type}")

		# List of items to link from --out/ directory
		items_to_link = []

		# Add HiFi-related files
		if self.data_type in ['hifi', 'mixed']:
			items_to_link.extend([
				'processed_reads',
				'HiFi.reads.stat',
				'hifi_reads.idx',
				'hifi_reads_part'
			])

		# Add ONT-related files
		if self.data_type in ['ont', 'mixed']:
			items_to_link.extend([
				'ONT.reads.stat',
				'ont_reads.idx',
				'ont_reads_part'
			])

		print(f"  Items to link: {items_to_link}")

		# Create symlinks for each item
		linked_count = 0
		missing_items = []
		for item_name in items_to_link:
			source = os.path.join(self.out, item_name)
			if os.path.exists(source):
				link = os.path.join(target_dir, item_name)

				# Remove existing link if present
				if os.path.exists(link) or os.path.islink(link):
					if os.path.islink(link):
						os.unlink(link)
					elif os.path.isfile(link):
						os.remove(link)
					elif os.path.isdir(link):
						import shutil
						shutil.rmtree(link)

				# Create symlink or copy
				try:
					# Use absolute paths for symlinks
					source_abs = os.path.abspath(source)
					if os.path.isdir(source):
						os.symlink(source_abs, link, target_is_directory=True)
					else:
						os.symlink(source_abs, link)
					linked_count += 1
					print(f"  ✓ Created symlink: {item_name}")
				except OSError as e:
					# Windows may not support symlinks, fall back to copying
					print(f"  ⚠ Symlink failed for {item_name} ({e}), copying instead...")
					import shutil
					if os.path.isdir(source):
						shutil.copytree(source, link)
					else:
						shutil.copy2(source, link)
					linked_count += 1
					print(f"  ✓ Copied: {item_name}")
			else:
				missing_items.append(item_name)

		if linked_count > 0:
			print(f"  → Successfully linked {linked_count} preprocessed files")

		if missing_items:
			print(f"  ⚠ Missing items (not found in {self.out}): {missing_items}")

		if linked_count == 0 and len(items_to_link) > 0:
			print(f"  ⚠ WARNING: No files were linked! Check if preprocessed files exist in {self.out}")

		print()

	def setScaffold(self,seqout):
		file1=open(self.scaffoldSeq,'a')
		l='>Scaffold_'+str(self.scaffoldID)+"\t"+"DG"+str(self.projectID)+"\n"+seqout+"\n"
		file1.writelines(l)
		file1.close()
		file1=open(self.agp,'a')
		DGlist=["DG"+str(self.projectID)]
		DGlist+=self.DGUsedCtgList
		for iDG in DGlist:
			file2=open(self.agppwd,'r')
			for agppwd in file2:
				agppwd1=agppwd.rstrip().split('\t')
				if agppwd1[0]==iDG:
					file3=open(agppwd1[1],'r')
					for l in file3:
						lo="Scaffold_"+str(self.scaffoldID)+"("+"DG"+str(self.projectID)+")"+l
						file1.writelines(lo)
					file3.close()
			file2.close()
		file1.close()

	# ============================================================================
	# Edge Library Creation Methods
	# ============================================================================

	def _create_edge_library(self, edge_file, current_contig_id, direction, seedlen):
		"""
		创建edge library用于MUMmer比对
		存储完整contig/scaffold序列及其反向互补，简化后续直连结果整合
		
		Args:
			edge_file: ctgsEdge.fa的完整路径
			current_contig_id: 当前contig的ID（需要排除）
			direction: 'left' or 'right'
			seedlen: 用于提取比对片段的长度（仅用于直连检测时的片段提取）
		
		Returns:
			dict: {'contig_edges': count, 'scaffold_edges': count, 'total': count}
		"""
		edge_counts = {'contig_edges': 0, 'scaffold_edges': 0}
		temp_dir = os.path.dirname(edge_file)
		
		# ========== Part 1: 完整contigs及其反向互补 ==========
		contig_edges_file = os.path.join(temp_dir, "contig_edges.fa")
		
		if os.path.exists(self.projectTerminalCtg) and os.path.getsize(self.projectTerminalCtg) > 0:
			with open(contig_edges_file, 'w') as ft:
				for gseq in SeqIO.parse(self.projectTerminalCtg, 'fasta'):
					contig_id = gseq.id
					seq = gseq.seq
					seq_len = len(seq)
					
					# 存储完整contig（正向和反向互补）
					# 命名格式保持兼容：{contig_id}-edge-{direction} 用于标识比对端
					if direction == 'left':
						# Left延伸：需要检查其他contig的右端是否与seed左端overlap
						# 正向：该contig的右端可能overlap → 命名为 -edge-right
						ft.write(f">{contig_id}-edge-right\tlen:{seq_len}\n{str(seq)}\n")
						# 反向互补：原contig左端变成右端 → 命名为 -edge-left_rc
						ft.write(f">{contig_id}-edge-left_rc\tlen:{seq_len}\n{str(seq.reverse_complement())}\n")
						edge_counts['contig_edges'] += 2
					else:  # right
						# Right延伸：需要检查其他contig的左端是否与seed右端overlap
						# 正向：该contig的左端可能overlap → 命名为 -edge-left
						ft.write(f">{contig_id}-edge-left\tlen:{seq_len}\n{str(seq)}\n")
						# 反向互补：原contig右端变成左端 → 命名为 -edge-right_rc
						ft.write(f">{contig_id}-edge-right_rc\tlen:{seq_len}\n{str(seq.reverse_complement())}\n")
						edge_counts['contig_edges'] += 2
		
		# ========== Part 2: 完整scaffold及其反向互补 ==========
		scaffold_edges_file = os.path.join(temp_dir, "scaffold_edges.fa")
		used_scaffold_ids = self._get_used_scaffolds()
		
		if os.path.exists(self.scaffoldSeq) and os.path.getsize(self.scaffoldSeq) > 0:
			with open(scaffold_edges_file, 'w') as ft:
				for gseq in SeqIO.parse(self.scaffoldSeq, 'fasta'):
					scaffold_id = gseq.id
					
					# 从 scaffold 描述中提取 DG ID
					desc_parts = gseq.description.split('\t')
					scaffold_dg_id = desc_parts[1] if len(desc_parts) >= 2 else scaffold_id
					
					# 跳过当前 DG 和已使用的 scaffold
					if scaffold_dg_id == f"DG{self.projectID}" or scaffold_id in used_scaffold_ids:
						continue
					
					scaffold_seq = gseq.seq
					seq_len = len(scaffold_seq)
					
					# 存储完整scaffold（正向和反向互补）
					if direction == 'left':
						ft.write(f">{scaffold_id}-scaffold-edge-right\tlen:{seq_len}\n{str(scaffold_seq)}\n")
						ft.write(f">{scaffold_id}-scaffold-edge-left_rc\tlen:{seq_len}\n{str(scaffold_seq.reverse_complement())}\n")
					else:
						ft.write(f">{scaffold_id}-scaffold-edge-left\tlen:{seq_len}\n{str(scaffold_seq)}\n")
						ft.write(f">{scaffold_id}-scaffold-edge-right_rc\tlen:{seq_len}\n{str(scaffold_seq.reverse_complement())}\n")
					edge_counts['scaffold_edges'] += 2
		
		# ========== 合并所有 edges ==========
		files_to_merge = []
		if os.path.exists(contig_edges_file) and os.path.getsize(contig_edges_file) > 0:
			files_to_merge.append(contig_edges_file)
		if os.path.exists(scaffold_edges_file) and os.path.getsize(scaffold_edges_file) > 0:
			files_to_merge.append(scaffold_edges_file)
		
		if files_to_merge:
			subprocess.run(f"cat {' '.join(files_to_merge)} > {edge_file}", shell=True)
		else:
			open(edge_file, 'w').close()  # 创建空文件
		
		# 清理临时文件
		for tmp in ['right_edge.fa', 'left_edge.fa', 'left_rc_edge.fa', 'right_rc_edge.fa', 
					'contig_edges.fa', 'scaffold_edges.fa']:
			tmp_path = os.path.join(temp_dir, tmp)
			if os.path.exists(tmp_path):
				os.remove(tmp_path)
		
		edge_counts['total'] = edge_counts['contig_edges'] + edge_counts['scaffold_edges']
		
		print(f"[CtgLinker] Created edge library: {edge_file}")
		print(f"  Direction: {direction}")
		print(f"  Contig edges: {edge_counts['contig_edges']}")
		print(f"  Scaffold edges: {edge_counts['scaffold_edges']}")
		print(f"  Total edges: {edge_counts['total']}")
		
		return edge_counts

	# ============================================================================
	# Edge Library Real-time Update Methods
	# ============================================================================

	def _extract_used_contigs_from_gapfiller(self, gfout, direction):
		"""
		从GapFiller结果中提取已使用的contigs
		
		逻辑：
		1. 首先检查延伸阶段是否成功
		2. 如果延伸成功，使用延伸结果的 contig
		3. 如果延伸失败，再检查是否有 direct connection 可用
		
		Args:
			gfout: GapFiller对象
			direction: 'left' or 'right'
		
		Returns:
			list: 使用的contig IDs列表
		"""
		used_contigs = []
		
		# 保存 direct connection 信息（备用）
		direct_contig = None
		direct_final_file = os.path.join(gfout.out, f"{gfout.name}.direct.final.fa")
		process_log_file = os.path.join(gfout.out, "process.log")
		
		if os.path.exists(direct_final_file) and os.path.getsize(direct_final_file) > 0:
			# 从 process.log 中解析 Connected edge
			if os.path.exists(process_log_file):
				try:
					with open(process_log_file, 'r') as f:
						log_content = f.read()
						import re
						match = re.search(r'Connected edge:\s*(\S+)', log_content)
						if match:
							connected_edge = match.group(1)
							if '-edge-' in connected_edge:
								parts = connected_edge.split('-edge-')
								contig_id = parts[0]
								if not contig_id.startswith('DG') and not contig_id.startswith('Scaffold'):
									direct_contig = contig_id
									print(f"[CtgLinker] Found direct connection to: {direct_contig} (will use if extension fails)")
				except Exception as e:
					print(f"[CtgLinker] Warning: Error reading process.log: {e}")
		
		try:
			
			# 检查是否成功延伸
			# ✨ 修复：添加 None 检查避免 AttributeError
			extension_reads_ok = (gfout.Elongation.roundResult.ExtensionReads is not None and 
								  gfout.Elongation.roundResult.ExtensionReads.note == '')
			extension_contigs_ok = (gfout.Elongation.roundResult.ExtensionContigs is not None and
									'No extension contigs or reads found' not in gfout.Elongation.roundResult.ExtensionContigs.selectContigNote and
									"Reach the maximum Length" not in gfout.Elongation.roundResult.ExtensionContigs.selectContigNote)
			if extension_reads_ok and extension_contigs_ok:
				
				# 方法1：从linkedSequence的描述中解析
				if gfout.Elongation.roundResult.roundOutput.linkedSequenceNote != '':
					for gseq in SeqIO.parse(gfout.Elongation.roundResult.roundOutput.linkedSequence, 'fasta'):
						l0 = gseq.description
						l1 = l0.split('\t')
						for l11 in l1:
							l2 = l11.split(':')
							if l2[0] == "Aln":
								closectg = l2[1].split(';')
								target_id = closectg[-2]  # 最后一个字段是target ID
								
								# 解析target ID，提取contig ID
								# 格式: "Contig-1-edge-left" 或 "DG1-scaffold-edge-right"
								if '-edge-' in target_id:
									parts = target_id.split('-edge-')
									contig_id = parts[0]
									
									# 只收集原始contigs，不收集scaffolds
									if not contig_id.startswith('DG'):
										if contig_id not in used_contigs:
											used_contigs.append(contig_id)
											print(f"[CtgLinker] {direction} used contig: {contig_id}")
				
				# 方法2：从AGP文件解析（作为补充）
				if os.path.exists(gfout.agp):
					with open(gfout.agp, 'r') as f:
						for line in f:
							if line.strip() and not line.startswith('#'):
								parts = line.strip().split('\t')
								if len(parts) >= 6:
									seq_id = parts[5]  # AGP格式第6列是序列ID
									
									# 提取原始contig ID（排除方向标记）
									if 'Left' not in seq_id and 'Right' not in seq_id:
										# 去除edge标记
										if '-edge-' in seq_id:
											seq_id = seq_id.split('-edge-')[0]
										
										if not seq_id.startswith('DG') and seq_id not in used_contigs:
											used_contigs.append(seq_id)
											print(f"[CtgLinker] {direction} used contig (from AGP): {seq_id}")
		
			# ✨✨✨ 修复：无论延伸是否成功，只要有 direct connection 就应该记录 ✨✨✨
			# 原因：direct connection 表示 seed 与目标 contig 有直接 overlap
			# 即使延伸成功了，这个 overlap 关系仍然存在，目标 contig 应该被标记为已使用
			if direct_contig and direct_contig not in used_contigs:
				used_contigs.append(direct_contig)
				if extension_reads_ok and extension_contigs_ok:
					print(f"[CtgLinker] {direction} used contig (from direct connection, extension also succeeded): {direct_contig}")
				else:
					print(f"[CtgLinker] {direction} used contig (from direct connection, extension failed): {direct_contig}")
		
		except Exception as e:
			print(f"[WARNING] Error extracting used contigs from GapFiller: {e}")
			import traceback
			traceback.print_exc()
			
			# 异常情况下，如果有 direct connection，也使用它
			if direct_contig and direct_contig not in used_contigs:
				used_contigs.append(direct_contig)
				print(f"[CtgLinker] {direction} used contig (from direct connection, fallback): {direct_contig}")
		
		return used_contigs

	def _update_terminal_contigs(self, used_contigs):
		"""
		更新projectTerminalCtg，移除已使用的contigs
		
		Args:
			used_contigs: 已使用的contig IDs列表
		"""
		if not used_contigs:
			print("[CtgLinker] No contigs to remove from terminal list")
			return
		
		# 更新ctgUsedID
		for ctg_id in used_contigs:
			if ctg_id not in self.ctgUsedID:
				self.ctgUsedID.append(ctg_id)
		
		print(f"[CtgLinker] Updating projectTerminalCtg")
		print(f"  Removing contigs: {used_contigs}")
		print(f"  Total used contigs now: {len(self.ctgUsedID)}")
		
		# 重写projectTerminalCtg文件，排除已使用的contigs
		temp_file = self.projectTerminalCtg + '.temp'
		kept_count = 0
		removed_count = 0
		
		with open(temp_file, 'w') as ft:
			if os.path.exists(self.projectTerminalCtg):
				for gseq in SeqIO.parse(self.projectTerminalCtg, 'fasta'):
					if gseq.id not in self.ctgUsedID:
						ft.write(f">{gseq.description}\n{str(gseq.seq)}\n")
						kept_count += 1
					else:
						removed_count += 1
		
		# 替换原文件
		import shutil
		shutil.move(temp_file, self.projectTerminalCtg)
		
		print(f"  Kept: {kept_count} contigs")
		print(f"  Removed: {removed_count} contigs")
		print(f"  Updated: {self.projectTerminalCtg}")

	# ============================================================================
	# Phase 1.5: Scaffold-to-Scaffold Linking Methods
	# ============================================================================

	def _parse_used_file(self):
		"""
		解析used.txt文件，获取所有DG的状态
		
		Returns:
			dict: {
				'DG1': {'right_tag': '', 'left_tag': '**', 'contigs': ['Contig-1', 'Contig-2']},
				'DG2': {'right_tag': '', 'left_tag': '', 'contigs': ['Contig-3']},
				...
			}
		"""
		dg_status = {}
		
		if not os.path.exists(self.used):
			return dg_status
		
		with open(self.used, 'r') as f:
			for line in f:
				line = line.strip()
				if not line or line.startswith('#'):
					continue
				
				parts = line.split('\t')
				if len(parts) < 4:
					continue
				
				dg_id = parts[0]
				right_tag = parts[1]  # '' or '**'
				left_tag = parts[2]   # '' or '**'
				contig_list = parts[3].split(';') if parts[3] else []
				
				dg_status[dg_id] = {
					'right_tag': right_tag,
					'left_tag': left_tag,
					'contigs': contig_list
				}
		
		return dg_status

	def _detect_scaffold_linkage(self, alignment_target_id):
		"""
		检测alignment target是否为scaffold，并提取scaffold信息
		
		Args:
			alignment_target_id: MUMmer比对中的target ID
								格式可能是：
								- "Contig-1-edge-left" (原始contig)
								- "Scaffold_1-scaffold-edge-right" (scaffold)
		
		Returns:
			dict: {
				'is_scaffold': bool,
				'scaffold_id': str or None (e.g., 'Scaffold_1'),
				'linked_end': str or None ('left' or 'right'),
				'is_rc': bool (是否需要反向互补)
			}
		"""
		result = {
			'is_scaffold': False,
			'scaffold_id': None,
			'linked_end': None,
			'is_complete': False
		}
		
		# 检查是否为scaffold edge
		if '-scaffold-edge-' not in alignment_target_id:
			return result
		
		result['is_scaffold'] = True
		
		# 解析scaffold ID和连接端
		# 格式: "DG1-scaffold-edge-right" 或 "DG2-scaffold-edge-left_complete"
		parts = alignment_target_id.split('-scaffold-edge-')
		if len(parts) != 2:
			print(f"[WARNING] Unexpected scaffold edge format: {alignment_target_id}")
			return result
		
		result['scaffold_id'] = parts[0]  # e.g., "DG1"
		
		end_info = parts[1]  # e.g., "right", "left_rc", "right_rc"
		
		# 检查是否需要反向互补
		result['is_rc'] = '_rc' in end_info
		
		# 提取端点类型（去掉 _rc 后缀）
		if '_rc' in end_info:
			result['linked_end'] = end_info.replace('_rc', '')
		else:
			result['linked_end'] = end_info
		
		print(f"[CtgLinker] Detected scaffold linkage:")
		print(f"  Target: {alignment_target_id}")
		print(f"  Scaffold: {result['scaffold_id']}")
		print(f"  Linked end: {result['linked_end']}")
		print(f"  Is RC: {result['is_rc']}")
		
		return result

	def _mark_scaffold_as_used(self, scaffold_id):
		"""
		将 scaffold 标记为已使用，后续不应再出现在 edge library 中
		同时从 DG.scaffold.fa 中删除该 scaffold
		
		Args:
			scaffold_id: Scaffold ID (e.g., 'Scaffold_1')
		"""
		# 记录到 used.scaffolds.txt
		with open(self.usedScaffolds, 'a') as f:
			f.write(f"{scaffold_id}\n")
		print(f"[CtgLinker] Marked scaffold as used: {scaffold_id}")
		
		# 从 DG.scaffold.fa 中删除该 scaffold
		self._remove_scaffold_from_file(scaffold_id)
	
	def _remove_scaffold_from_file(self, scaffold_id):
		"""
		从 DG.scaffold.fa 中删除指定的 scaffold
		
		Args:
			scaffold_id: Scaffold ID (e.g., 'Scaffold_1')
		"""
		if not os.path.exists(self.scaffoldSeq):
			return
		
		temp_file = self.scaffoldSeq + '.temp'
		removed = False
		
		with open(temp_file, 'w') as fout:
			for gseq in SeqIO.parse(self.scaffoldSeq, 'fasta'):
				if gseq.id == scaffold_id:
					print(f"[CtgLinker] Removing scaffold from DG.scaffold.fa: {scaffold_id}")
					removed = True
					continue
				# 保留其他 scaffold
				fout.write(f">{gseq.description}\n{str(gseq.seq)}\n")
		
		# 替换原文件
		import shutil
		shutil.move(temp_file, self.scaffoldSeq)
		
		if removed:
			print(f"[CtgLinker] Scaffold {scaffold_id} removed from final results")

	def _get_scaffold_agp_components(self, scaffold_id):
		"""
		从 DG.scaffold.agp 中获取指定 scaffold 的所有组件（contigs）
		
		Args:
			scaffold_id: Scaffold ID (e.g., 'Scaffold_1')
		
		Returns:
			list: AGP 行列表，每行是该 scaffold 的一个组件
		"""
		components = []
		if not os.path.exists(self.agp):
			return components
		
		with open(self.agp, 'r') as f:
			for line in f:
				if line.startswith('#') or not line.strip():
					continue
				# AGP 格式: Scaffold_1(DG1)DG1	start	end	...
				# 检查是否属于目标 scaffold
				if line.startswith(scaffold_id + '(') or line.startswith(scaffold_id + '\t'):
					components.append(line.strip())
		
		print(f"[CtgLinker] Found {len(components)} AGP components for {scaffold_id}")
		return components

	def _get_used_scaffolds(self):
		"""
		获取已使用的 scaffold ID 集合
		
		Returns:
			set: 已使用的 scaffold ID 集合
		"""
		used = set()
		if os.path.exists(self.usedScaffolds):
			with open(self.usedScaffolds, 'r') as f:
				for line in f:
					line = line.strip()
					if line and not line.startswith('#'):
						used.add(line)
		return used

	def setGapFiller(self):
		outdict={}
		
		# ✨✨✨ 防御性检查：确保 roundInputSeq 不为 None ✨✨✨
		if self.roundInputSeq is None:
			print(f"[CtgLinker] Error: roundInputSeq is None in setGapFiller, skipping")
			self.outdict = outdict
			return
		
		# 获取当前contig ID（用于从edge library中排除）
		current_contig_id = self.roundInputSeq.id
		
		# 获取seed长度（统一使用hifiSeedLen，与N50Check保持一致）
		if self.data_type == 'ont':
			seedlen = int(self.ontSeedLen) if self.ontSeedLen else int(self.hifiSeedLen)
			print(f"[CtgLinker] Using ONT seedLen: {seedlen} bp")
		else:  # hifi or mixed
			# mixed模式也使用hifiSeedLen，因为N50Check是基于hifiSeedLen过滤的
			seedlen = int(self.hifiSeedLen)
			print(f"[CtgLinker] Using HiFi seedLen: {seedlen} bp")
		
		for flag1 in self.flaglist:
			for gseq in SeqIO.parse(self.roundInputSeqFile,'fasta'):
				leftID=''
				rightID=''
				if 'DG' not in gseq.id:
					chrID=gseq.description.split('\t')[-1]
					contigID=int(gseq.id.split('-')[-1])
					for gseq1 in SeqIO.parse(self.projectTerminalCtg,'fasta'):
						# Skip DG scaffolds when looking for adjacent contigs
						if 'DG' in gseq1.id:
							continue
						chrID1=gseq1.description.split('\t')[-1]
						contigID1=int(gseq1.id.split('-')[-1])
						if chrID1==chrID:
							if contigID1==(contigID+1):
								leftID=gseq1.id
							if contigID1==(contigID-1):
								rightID=gseq1.id
				else:
					# DG scaffold handling
					print (gseq.description)
					desc_parts = gseq.description.split('\t')
					
					# Extract chrID safely
					if len(desc_parts) >= 2:
						chrID = desc_parts[-2] if len(desc_parts) > 2 else desc_parts[-1]
					else:
						chrID = desc_parts[0] if desc_parts else ''
					
					# Extract contig IDs
					if len(desc_parts) >= 3:
						contigID = desc_parts[-3].split(';')
					else:
						contigID = []
					
					contigIDright=''
					contigIDleft=''
					
					if contigID and 'Right' not in contigID[0] and len(contigID[0].split('-'))!=1:
						print (contigID[0])
						if 'DG' not in contigID[0]:  # Only parse if it's a contig, not a DG
							contigIDright=int(contigID[0].split('-')[1])
					
					if contigID and 'Left' not in contigID[-1] and len(contigID[-1].split('-'))!=1:
						if 'DG' not in contigID[-1]:  # Only parse if it's a contig, not a DG
							contigIDleft=int(contigID[-1].split('-')[1])
					for gseq1 in SeqIO.parse(self.projectTerminalCtg,'fasta'):
						# Skip DG scaffolds when looking for adjacent contigs
						if 'DG' in gseq1.id:
							continue
						chrID1=gseq1.description.split('\t')[-1]
						contigID1=int(gseq1.id.split('-')[-1])
						if chrID1==chrID:
							if contigIDleft!='':
								if contigID1==(contigIDleft+1):
									leftID=gseq1.id
							if contigIDright!='':
								if contigID1==(contigIDright-1):
									rightID=gseq1.id
					
				
					
			if flag1=='left':
				projectoutEX=self.projectOut+"/DG"+str(self.projectID)+"-Left"
			else:
				projectoutEX=self.projectOut+"/DG"+str(self.projectID)+"-Right"
			if not os.path.exists(projectoutEX):
				os.makedirs(projectoutEX)

			# Create symlinks to preprocessed reads files in the subtask directory
			self._create_reads_symlinks(projectoutEX)

			# ========== 优化：直接使用完整序列，让GapFillerClass自己提取seed ==========
			# GapFillerClass的InputSequence会根据flag自动从roundInputSeqFile提取seed
			# 无需手动预提取seed片段
			
			# ========== 核心改进：创建edge library（包含contigs + scaffold双端）==========
			self.ctgsEdgeFile = self.projectData + "/ctgsEdge.fa"
			edge_counts = self._create_edge_library(
				self.ctgsEdgeFile,
				current_contig_id,
				flag1,
				seedlen
			)

			# Check if edge library has any sequences
			if edge_counts['total'] == 0:
				print(f"\n{'='*80}")
				print(f"INFO: No edge sequences found in {self.ctgsEdgeFile}")
				print(f"This means there are no other contigs available for linking with the current contig.")
				print(f"Skipping {flag1} extension for DG{self.projectID} as there are no contigs to link.")
				print(f"{'='*80}\n")

				# Create a minimal output to indicate no extension was possible
				# This prevents downstream errors when checking results
				class MinimalGapFillerOutput:
					def __init__(self, project_out, flag):
						self.out = project_out
						self.flag = flag
						self.initialSeq = None
						self.agp = project_out + f"/no_extension_{flag}.agp"

						# Create minimal Elongation object
						class MinimalElongation:
							def __init__(self):
								class MinimalRoundResult:
									def __init__(self):
										class MinimalExtensionReads:
											def __init__(self):
												self.note = 'No edge sequences available for linking'
										class MinimalExtensionContigs:
											def __init__(self):
												self.selectContigNote = 'No extension contigs or reads found - no edge sequences available'
										class MinimalRoundOutput:
											def __init__(self):
												self.linkedSequenceNote = ''
										self.ExtensionReads = MinimalExtensionReads()
										self.ExtensionContigs = MinimalExtensionContigs()
										self.roundOutput = MinimalRoundOutput()
								self.roundResult = MinimalRoundResult()
						self.Elongation = MinimalElongation()

				outdict[flag1] = MinimalGapFillerOutput(projectoutEX, flag1)
				continue  # Skip to next flag in flaglist

			# Create list containing k-mer parameters
			kparameters = [self.kmer_size, self.kmer_num, self.kmer_filter]

			# ========== 优化：使用完整序列文件作为initialSeq ==========
			# GapFiller的flag逻辑（重要！）：
			#  - flag='left': 从seqleft提取右端seed，向右延伸到seqright
			#  - flag='right': 从seqright提取左端seed，向左延伸到seqleft
			# 
			# CtgLinker的需求：
			#  - flag1='left': 从contig左端向左延伸 → 需要GapFiller flag='right'
			#  - flag1='right': 从contig右端向右延伸 → 需要GapFiller flag='left'
			
			if flag1 == 'left':
				# Left延伸：从contig左端向左延伸
				# → 需要提取contig左端 → flag='right', seqright=contig
				seqleft_param = self.ctgsEdgeFile
				seqright_param = self.roundInputSeqFile
				gapfiller_flag = 'right'  # 反转！
			else:  # right
				# Right延伸：从contig右端向右延伸
				# → 需要提取contig右端 → flag='left', seqleft=contig
				seqleft_param = self.roundInputSeqFile
				seqright_param = self.ctgsEdgeFile
				gapfiller_flag = 'left'  # 反转！
			
			# Build GapFiller parameter list in new format (21 parameters)
			# [mode, remove, thread, reads, out, seqleft, seqright, flag, edge,
			#  filterDepthHifi, filterDepthOnt, MaximumExtensionLength, MaximumExtensionRound,
			#  data_type, ont_reads, readsDict, maxReadsLen, hifiSeedLen, ontSeedLen,
			#  original_reads_info, ont_readsDict]
			gf_params = [
				self.mode, self.remove, self.thread, self.reads, projectoutEX,
				seqleft_param, seqright_param, gapfiller_flag, self.edge,  # ← 使用反转后的flag
				self.filterDepthHifi, self.filterDepthOnt, self.MaximunExtensionLength,
				self.MaximumExtensionRound,
				self.data_type, self.ont_reads, self.readsDict, self.maxReadsLen,
				self.hifiSeedLen, self.ontSeedLen,  # Pass dual seed lengths
				self.original_reads_info, self.ont_readsDict  # Pass original reads info and ONT readsDict
			]

			print(f"[CtgLinker] Calling GapFiller with complete sequence")
			print(f"  CtgLinker direction: {flag1}")
			print(f"  GapFiller flag: {gapfiller_flag} (reversed!)")
			print(f"  Complete sequence: {self.roundInputSeqFile}")
			print(f"  Edge library: {self.ctgsEdgeFile} ({edge_counts['total']} edges)")
			print(f"    - Contig edges: {edge_counts['contig_edges']}")
			print(f"    - Scaffold edges: {edge_counts['scaffold_edges']}")
			print(f"  GapFiller params: seqleft={seqleft_param}, seqright={seqright_param}, flag={gapfiller_flag}")
			print(f"  Note: GapFillerClass will extract seed from {'seqright' if gapfiller_flag=='right' else 'seqleft'}")

			gfout = GapFiller(gf_params, kparameters)
			outdict[flag1]=gfout
			
			# ✨✨✨ 新增：GapFiller 完成后立即生成可视化报告 ✨✨✨
			try:
				from GapfillerVisualizer import GapfillerLogParser, HTMLReportGenerator
				process_log = projectoutEX + "/process.log"
				if os.path.exists(process_log):
					visualization_output = projectoutEX + "/visualization_output"
					if not os.path.exists(visualization_output):
						os.makedirs(visualization_output)
					
					parser = GapfillerLogParser(process_log, result_dir=projectoutEX)
					parsed_data = parser.parse_log()
					generator = HTMLReportGenerator(
						parsed_data, 
						visualization_output, 
						result_dir=projectoutEX,
						extension_flag=gapfiller_flag,
						max_extension_length=int(self.MaximunExtensionLength) if self.MaximunExtensionLength else None
					)
					report_path = generator.generate_report()
					print(f"[CtgLinker] Generated GapFiller report: {report_path}")
			except Exception as e:
				print(f"[CtgLinker] Warning: Failed to generate GapFiller report: {e}")
			
			# ✨✨✨ 新增：立即更新edge library ✨✨✨
			print(f"\n[CtgLinker] Checking for used contigs in {flag1} direction...")
			used_contigs = self._extract_used_contigs_from_gapfiller(gfout, flag1)
			
			if used_contigs:
				print(f"[CtgLinker] {flag1} direction used {len(used_contigs)} contig(s)")
				self._update_terminal_contigs(used_contigs)
				print(f"[CtgLinker] Edge library updated for next direction\n")
			else:
				print(f"[CtgLinker] {flag1} direction did not use any new contigs\n")
			
			# ✨ 修复：添加 None 检查避免 AttributeError
			extension_reads_ok = (gfout.Elongation.roundResult.ExtensionReads is not None and 
								  gfout.Elongation.roundResult.ExtensionReads.note == '')
			extension_contigs_ok = (gfout.Elongation.roundResult.ExtensionContigs is not None and
									'No extension contigs or reads found' not in gfout.Elongation.roundResult.ExtensionContigs.selectContigNote and
									"Reach the maximum Length" not in gfout.Elongation.roundResult.ExtensionContigs.selectContigNote and
									"Reached maximum extension rounds" not in gfout.Elongation.roundResult.ExtensionContigs.selectContigNote)
			if extension_reads_ok and extension_contigs_ok:
				# Use the same seedlen as used for edge extraction (already calculated above)
				# seedlen variable is still in scope from lines 718-729
				if gfout.Elongation.roundResult.roundOutput.linkedSequenceNote!='':
					for gseq in SeqIO.parse(gfout.Elongation.roundResult.roundOutput.linkedSequence,'fasta'):
						l0=gseq.description
						l1=l0.split('\t')
						for l11 in l1:
							l2=l11.split(':')
							if l2[0]=="Aln":
								closectg=l2[1].split(';')
								TS=closectg[-2]
					
					# ========== 检测是否连接到scaffold ==========
					scaffold_info = self._detect_scaffold_linkage(TS)
					
					if scaffold_info['is_scaffold']:
						print(f"\n[CtgLinker] ⚠ Scaffold linkage detected!")
						print(f"  Current DG: DG{self.projectID}")
						print(f"  Target scaffold: {scaffold_info['scaffold_id']}")
						print(f"  Linked end: {scaffold_info['linked_end']}")
						print(f"  Direction: {flag1}")
						print(f"  Note: This direction will be marked as '**' (inheriting scaffold's completed status)")
						
						# 标记 scaffold 为已使用，后续不应再出现在 edge library 中
						self._mark_scaffold_as_used(scaffold_info['scaffold_id'])
					
					# 继续常规contig linkage处理
					if scaffold_info['is_scaffold']:
						# 如果是scaffold，TS格式为 "Scaffold_1-scaffold-edge-right"
						# 需要从 scaffoldSeq 中获取序列
						target_id = scaffold_info['scaffold_id']
						linked_end = scaffold_info['linked_end']  # 'left' or 'right'
						
						# 构造 TS1，模拟 contig 的格式以便后续处理
						# TS1[0] = scaffold ID, TS1[1] = edge 类型（用于判断方向）
						TS1 = [target_id, linked_end]  # e.g., ["Scaffold_1", "right"]
						
						TSSeq = None
						for gseq in SeqIO.parse(self.scaffoldSeq, 'fasta'):
							if gseq.id == target_id:
								TSSeq = gseq
								break
						
						if TSSeq is None:
							print(f"[ERROR] Could not find scaffold sequence {target_id} in {self.scaffoldSeq}")
							# Fallback or exit? For now let it crash or handle gracefully
					else:
						# 常规 contig
						TS1=TS.split("-edge-")
						# ✨ 修复：检查 TS1 是否有足够的元素
						if len(TS1) < 2:
							print(f"[WARNING] Unexpected edge format: {TS}")
							print(f"  Expected format: 'ContigID-edge-direction' (e.g., 'Contig-1-edge-left')")
							print(f"  Got: {TS1}")
							# 尝试使用默认方向
							TS1 = [TS1[0] if TS1 else TS, 'forward']
						TSSeq = None
						for gseq in SeqIO.parse(self.ctgSeq,'fasta'):
							if gseq.id==TS1[0]:
								TSSeq=gseq
								break
					
					if TSSeq is None:
						print(f"[ERROR] Target sequence not found for {TS}")
						continue

					for gseq in SeqIO.parse(self.ctgSeq,'fasta'):
						if gseq.id==self.roundInputSeq.id:
							ISSeq=gseq
					for gseq in SeqIO.parse(gfout.Elongation.finalSeq,'fasta'):
						GSseq=gseq

					# 处理反向互补
					if len(TS1) > 1 and ('reverse' in TS1[1] or '_rc' in TS1[1]):
						TSSeqS=TSSeq.seq.reverse_complement()
					else:
						TSSeqS=TSSeq.seq
					
					# 序列整合逻辑
					# 序列整合逻辑
					# GapFiller 输出 GSseq 的结构：
					#   flag1='left': [目标edge截去共线区段] + [完整seed contig]
					#   flag1='right': [完整seed contig] + [目标edge截去共线区段]
					# 
					# CtgLinker 需要整合 GSseq 与完整的目标 contig/scaffold：
					#   flag1='left': 目标contig[:-seedlen] + GSseq（目标在左边）
					#   flag1='right': GSseq + 目标contig[seedlen:]（目标在右边）
					
					if scaffold_info['is_scaffold']:
						# Scaffold 连接
						linked_end = scaffold_info['linked_end']
						is_rc = scaffold_info.get('is_rc', False)
						
						# 如果是 _rc 类型，需要对 scaffold 做反向互补
						if is_rc:
							TSSeqS = TSSeq.seq.reverse_complement()
						else:
							TSSeqS = TSSeq.seq
						
						if flag1=='left':
							# 向左延伸，GSseq左端包含目标scaffold的edge部分
							# 整合：scaffold[:-seedlen] + GSseq
							SeqFinal=TSSeqS[:-int(seedlen)]+GSseq.seq
							addlen=len(TSSeqS[:-int(seedlen)])
						else:  # flag1=='right'
							# 向右延伸，GSseq右端包含目标scaffold的edge部分
							# 整合：GSseq + scaffold[seedlen:]
							SeqFinal=GSseq.seq+TSSeqS[int(seedlen):]
							addlen=len(TSSeqS[int(seedlen):])
					else:
						# 常规 contig 连接
						if flag1=='left':
							# 向左延伸，GSseq左端包含目标contig的edge部分
							# 整合：contig[:-seedlen] + GSseq
							SeqFinal=TSSeqS[:-int(seedlen)]+GSseq.seq
							addlen=len(TSSeqS[:-int(seedlen)])
						else:
							# 向右延伸，GSseq右端包含目标contig的edge部分
							# 整合：GSseq + contig[seedlen:]
							SeqFinal=GSseq.seq+TSSeqS[int(seedlen):]
							addlen=len(TSSeqS[int(seedlen):])
	
					filet=open(gfout.agp,'r')
					lage=''
					
					# 如果连接到 scaffold，获取其 AGP 组件用于展开
					scaffold_agp_components = []
					if scaffold_info['is_scaffold']:
						scaffold_agp_components = self._get_scaffold_agp_components(TS1[0])
						is_rc = '_rc' in TS1[1] or 'reverse' in TS1[1]
						if is_rc:
							# 反向互补时，需要反转组件顺序
							scaffold_agp_components = list(reversed(scaffold_agp_components))
						print(f"[CtgLinker] Expanding scaffold {TS1[0]} with {len(scaffold_agp_components)} components (reversed={is_rc})")
					
					for row in filet:
						lt=''
						row1=row.rstrip().split('\t')
						if flag1=='left':
							if TS1[0] in row:
								# 这里是连接点，需要展开 scaffold 的 contigs
								if scaffold_info['is_scaffold'] and scaffold_agp_components:
									# 展开 scaffold 的所有组件（包括 contigs 和 gap_fill）
									for sc_line in scaffold_agp_components:
										sc_parts = sc_line.split('\t')
										if len(sc_parts) >= 6:
											# 提取组件 ID（第6列）
											comp_id = sc_parts[5]
											# 保留所有组件（contigs 和 gap_fill 标记）
											lt=row1[0]+"\t"+row1[1]+"\t"+str(len(SeqFinal))+"\t"+row1[3]+"\t"+row1[4]+"\t"+comp_id+"\t"+(sc_parts[6] if len(sc_parts)>6 else "1")+"\t"+(sc_parts[7] if len(sc_parts)>7 else str(addlen))
											orientation = sc_parts[8] if len(sc_parts) > 8 else '+'
											if is_rc:
												orientation = '-' if orientation == '+' else '+'
											lt=lt+"\t"+orientation+"\n"
											lage+=lt
									# 添加当前 DG 的连接标记（Scaffold 和 seed 之间的连接点）
									dg_link_id = f"DG{self.projectID}-Left-linked-{TS1[0]}"
									lt=row1[0]+"\t"+row1[1]+"\t"+str(len(SeqFinal))+"\t"+row1[3]+"\t"+row1[4]+"\t"+dg_link_id+"\t1\t1\t+\n"
									lage+=lt
								else:
									lt=row1[0]+"\t"+row1[1]+"\t"+str(len(SeqFinal))+"\t"+row1[3]+"\t"+row1[4]+"\t"+TS1[0]+"\t"+row1[6]+"\t"+str(int(row1[7])+addlen)
									if 'reverse' in TS1[1]:
										lt=lt+"\t-\n"
									else:
										lt=lt+"\t+\n"
									lage+=lt
							else:
								lage+=row
						else:
							if TS1[0] in row:
								# 这里是连接点，需要展开 scaffold 的 contigs
								if scaffold_info['is_scaffold'] and scaffold_agp_components:
									# 添加当前 DG 的连接标记（seed 和 Scaffold 之间的连接点）
									dg_link_id = f"DG{self.projectID}-Right-linked-{TS1[0]}"
									lt=row1[0]+"\t"+row1[1]+"\t"+str(int(row1[7])+addlen)+"\t"+row1[3]+"\t"+row1[4]+"\t"+dg_link_id+"\t1\t1\t+\n"
									lage+=lt
									# 展开 scaffold 的所有组件（包括 contigs 和 gap_fill）
									for sc_line in scaffold_agp_components:
										sc_parts = sc_line.split('\t')
										if len(sc_parts) >= 6:
											comp_id = sc_parts[5]
											# 保留所有组件（contigs 和 gap_fill 标记）
											lt=row1[0]+"\t"+row1[1]+"\t"+str(int(row1[7])+addlen)+"\t"+row1[3]+"\t"+row1[4]+"\t"+comp_id+"\t"+(sc_parts[6] if len(sc_parts)>6 else "1")+"\t"+(sc_parts[7] if len(sc_parts)>7 else str(addlen))
											orientation = sc_parts[8] if len(sc_parts) > 8 else '+'
											if is_rc:
												orientation = '-' if orientation == '+' else '+'
											lt=lt+"\t"+orientation+"\n"
											lage+=lt
								else:
									lt=row1[0]+"\t"+row1[1]+"\t"+str(int(row1[7])+addlen)+"\t"+row1[3]+"\t"+row1[4]+"\t"+TS1[0]+"\t"+row1[6]+"\t"+str(int(row1[7])+addlen)
									if 'reverse' in TS1[1]:
										lt=lt+"\t-\n"
									else:
										lt=lt+"\t+\n"
									lage+=lt
							else:
								if row1[5]==GSseq.id:
									lt=row1[0]+"\t"+str(int(row1[1])+addlen)+"\t"+str(int(row1[2])+addlen)+"\t"+row1[3]+"\t"+row1[4]+"\t"+row1[5]+"\t"+str(int(row1[6])+addlen)+"\t"+str(int(row1[7])+addlen)+"\t+\n"
								else:
									lt=row1[0]+"\t"+str(int(row1[1])+addlen)+"\t"+str(int(row1[2])+addlen)+"\t"+"\t".join(row1[3:7])+"\t"+str(len(self.roundInputSeq.seq))+"\t+\n"
								lage+=lt
						
						if len(SeqFinal)!=len(GSseq.seq)+addlen:
							print ('linkage err')
							sys.exit()
					filet.close()
					filet=open(gfout.agp,'w')
					filet.writelines(lage)
					filet.close()
					filet=open(gfout.Elongation.finalSeq,'w')
					lo='>'+GSseq.description+"\n"+SeqFinal+"\n"
					filet.writelines(lo)
					filet.close()
		
		# 循环结束后统一赋值（移到循环外）
		self.outdict = outdict
		
		# Memory cleanup after processing all directions
		self._cleanup_gapfiller_memory(outdict)

	def _cleanup_gapfiller_memory(self, outdict):
		"""Clean up GapFiller memory after processing to prevent memory accumulation"""
		import gc
		
		for flag, gfout in outdict.items():
			if hasattr(gfout, 'Elongation'):
				elong = gfout.Elongation
				# Clear round results
				if hasattr(elong, 'roundResult'):
					rr = elong.roundResult
					if hasattr(rr, 'ExtensionReads'):
						er = rr.ExtensionReads
						for attr in ['minimumThresholdReadsID', 'minimumThresholdExtensionReadsID', 
									 'selectPotentialExtensionReadsID', 'extensionReadsID']:
							if hasattr(er, attr):
								setattr(er, attr, [])
					if hasattr(rr, 'ExtensionContigs'):
						ec = rr.ExtensionContigs
						if hasattr(ec, 'hifiasmResultDict'):
							ec.hifiasmResultDict = {}
				# Clear used reads list
				if hasattr(elong, 'usedReads'):
					elong.usedReads = []
				if hasattr(elong, 'lastRoundUsedReads'):
					elong.lastRoundUsedReads = []
		
		# Force garbage collection
		gc.collect()
		print(f"[CtgLinker] Memory cleanup completed for DG{self.projectID}")

	def _cleanup_between_dgs(self):
		"""Clean up memory between DG processing to prevent memory accumulation"""
		import gc
		
		# Clear outdict from previous DG
		if hasattr(self, 'outdict'):
			# First clean up GapFiller objects
			if self.outdict:
				self._cleanup_gapfiller_memory(self.outdict)
			# Then remove the reference
			self.outdict = {}
		
		# Clear other large data structures
		if hasattr(self, 'roundInputSeq'):
			self.roundInputSeq = None
		if hasattr(self, 'ctgsEdgeSeq'):
			self.ctgsEdgeSeq = None
		if hasattr(self, 'DGUsedCtgList'):
			self.DGUsedCtgList = []
		
		# Force garbage collection
		gc.collect()
		print(f"[CtgLinker] Memory cleanup between DGs completed (after DG{self.projectID - 1})")

	def elongationDGInit(self):
		self.elongationDGInitLog=self.projectOut+"/DG"+str(self.projectID)+".input.log"
		if os.path.exists(self.projectTerminalCtg)!=True or os.path.getsize(self.projectTerminalCtg)==0 or os.path.getsize(self.elongationDGInitLog)==0 or os.path.exists(self.elongationDGInitLog)!=True:
			logfile=open(self.elongationDGInitLog,'w')
			self.ctgUsedID=[]
			self.TerminalCtgID=[]
			
			# 从 used.txt 收集已使用的 contig IDs（用集合提高查找效率）
			ctgUsedSet = set()
			with open(self.used, 'r') as fileDGn:
				for line in fileDGn:
					if line.startswith('#'):
						continue
					parts = line.rstrip().split('\t')
					if len(parts) < 4:
						continue
					for ctg in parts[3].split(';'):
						# 跳过空字符串和失败/状态标记
						if not ctg or ctg in ('noExtensionContigsorReads', 'noNewExtensionReads', 'reachMaximumLength'):
							continue
						
						# 提取原始 contig ID（去除 -edge- 后缀）
						if '-edge-' in ctg:
							ctg = ctg.split('-edge-')[0]
						
						# 跳过方向标记（DG1-Right-xxx, DG1-Left-xxx）
						if 'Left' in ctg or 'Right' in ctg:
							continue
						
						# 跳过 scaffold 标记
						if '-scaffold-' in ctg:
							continue
						
						# 添加原始 contig 或其他 DG（排除当前行的 DG ID）
						if ctg != parts[0]:
							ctgUsedSet.add(ctg)
			
			self.ctgUsedID = list(ctgUsedSet)
			print(self.ctgUsedID, 'self.ctgUsedID')
			
			# 使用 seqkit 过滤：从原始contigs中排除已使用的
			# terminalCtg 只包含未使用的原始 contigs
			excludeIDFile = self.projectData + "/exclude_ids.txt"
			with open(excludeIDFile, 'w') as f:
				f.write('\n'.join(self.ctgUsedID))
			
			if os.path.getsize(excludeIDFile) > 0:
				# 有需要排除的ID，使用seqkit grep -v 过滤
				cmd = f"seqkit grep -v -f {excludeIDFile} {self.ctgSeq} -o {self.projectTerminalCtg}"
			else:
				# 没有需要排除的ID，直接复制
				cmd = f"seqkit seq {self.ctgSeq} -o {self.projectTerminalCtg}"
			
			print(f"[CtgLinker] Running: {cmd}")
			result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
			if result.returncode != 0:
				print(f"[CtgLinker] seqkit error: {result.stderr}")
				# 回退到原始方法
				print("[CtgLinker] Falling back to BioPython method...")
				with open(self.projectTerminalCtg, 'w') as file1:
					for gseq in SeqIO.parse(self.ctgSeq, 'fasta'):
						if gseq.id not in ctgUsedSet:
							file1.write(f'>{gseq.description}\n{gseq.seq}\n')
			
			# ✨✨✨ 修复：检查terminalCtg是否为空 ✨✨✨
			if os.path.getsize(self.projectTerminalCtg) == 0:
				print(f"[CtgLinker] No contigs available for DG{self.projectID}, terminating")
				logfile.close()
				self.Lastround = True
				self.unplacednum = 0  # 强制终止循环
				return ""  # 返回空字符串
			
			self.FindInputSeq()

			# ✨✨✨ 修复：检查 FindInputSeq 是否成功找到 seed ✨✨✨
			if self.roundInputSeq is None:
				print(f"[CtgLinker] No seed contig found for DG{self.projectID}, terminating pipeline")
				logfile.close()
				self.Lastround = True
				self.unplacednum = 0  # 强制终止循环
				self.skipCurrentDG = True  # 标记跳过当前 DG
				return ""  # 返回空字符串

			LogLine="projectTerminalCtg\t"+str(self.projectTerminalCtg)+"\n"
			LogLine+="TerminalCtgID\t"+";".join(self.TerminalCtgID)+"\n"
			LogLine+="projectused\t"+str(self.projectused)+"\n"
			LogLine+="ctgUsedID\t"+";".join(self.ctgUsedID)+"\n"
			LogLine+="flaglist\t"+";".join(self.flaglist)+"\n"

			LogLine+="roundInputSeqFile\t"+str(self.roundInputSeqFile)+"\n"
			LogLine+="roundInputSeqID\t"+str(self.roundInputSeq.id)+"\n"
			self.roundInputSeqLength = len(self.roundInputSeq.seq)  # 设置属性供合并时使用
			LogLine+="roundInputSeqLength\t"+str(self.roundInputSeqLength)+"\n"
			
			logfile.writelines(LogLine)
			logfile.close()
			return LogLine
		else:
			logfile=open(self.elongationDGInitLog,'r')
			LogLine=''
			for row in logfile:
				LogLine+=row
				row1=row.rstrip().split('\t')
				if row1[0]=='projectTerminalCtg':
					self.projectTerminalCtg=row1[1]
				elif row1[0]=='TerminalCtgID':
					if len(row1)>1:
						self.TerminalCtgID=row1[1].split(';')
					else:
						self.TerminalCtgID=[]
				elif row1[0]=='projectused':
					self.projectused=row1[1]
				elif row1[0]=='ctgUsedID':
					if len(row1)>1:
						self.ctgUsedID=row1[1].split(';')
					else:
						self.ctgUsedID=[]
				elif row1[0]=='flaglist':
					self.flaglist=row1[1].split(';')
				elif row1[0]=='roundInputSeqFile':
					self.roundInputSeqFile=row1[1]
					for gseq in SeqIO.parse(self.roundInputSeqFile,'fasta'):
						self.roundInputSeq=gseq
				elif row1[0]=='roundInputSeqLength':
					self.roundInputSeqLength=int(row1[1])
			logfile.close()
			
			# ✨✨✨ 修复：从日志恢复后也要检查 roundInputSeq ✨✨✨
			if self.roundInputSeq is None:
				print(f"[CtgLinker] No seed contig found from log for DG{self.projectID}, terminating pipeline")
				self.Lastround = True
				self.unplacednum = 0
				self.skipCurrentDG = True
				return ""
			
			return LogLine
					
	def FindInputSeq(self):
		self.roundInputSeqFile=self.projectData+"/DG"+str(self.projectID)+".input.fa"
		lenm=0
		self.roundInputSeq=None  # Initialize roundInputSeq
		
		# ✨✨✨ 修复：先收集已被吸收的 DG，避免选择它们作为 seed ✨✨✨
		absorbed_dgs = set()  # 已被其他 DG 吸收的 DG 集合
		fileDGn=open(self.used,'r')
		for i in fileDGn:
			if i[0]=="#":
				continue
			i1=i.rstrip().split('\t')
			if len(i1) < 4:
				continue
			tags = i1[3].split(';')
			for tag in tags:
				# 检查 tag 是否是 DG ID（被当前 DG 吸收）
				import re
				dg_match = re.match(r'^(DG\d+)', tag)
				if dg_match:
					absorbed_dg = dg_match.group(1)
					if absorbed_dg != i1[0]:  # 排除自身
						absorbed_dgs.add(absorbed_dg)
		fileDGn.close()
		
		if absorbed_dgs:
			print(f"[CtgLinker] DGs already absorbed by others: {absorbed_dgs}")
		
		# 优先选择未完成的 DG（从 DG.project.fa）
		# 未完成的 DG：在 used.txt 中存在，且两端不全是 **，且未被其他 DG 吸收
		fileDGn=open(self.used,'r')
		for i in fileDGn:
			if i[0]=="#":
				continue
			i1=i.rstrip().split('\t')
			if len(i1) < 4:
				continue
			dg_id = i1[0]
			right_status = i1[1]
			left_status = i1[2]
			
			# ✨ 跳过已被其他 DG 吸收的 DG
			if dg_id in absorbed_dgs:
				print(f"[CtgLinker] Skipping {dg_id}: already absorbed by another DG")
				continue
			
			# 检查是否未完成（两端不全是 **）
			if right_status != '**' or left_status != '**':
				# 找到未完成的 DG，从 projectSeq 获取序列
				for gseq in SeqIO.parse(self.projectSeq,'fasta'):
					if gseq.id == dg_id:
						self.roundInputSeq = gseq
						lenm = len(gseq.seq)
						print(f"[CtgLinker] Found incomplete DG: {dg_id} (right={right_status}, left={left_status})")
						break
				if self.roundInputSeq is not None:
					break
		fileDGn.close()
		
		# 如果没有未完成的 DG，从原始 contigs 中选择最长的
		if self.roundInputSeq is None:
			# 使用 seqkit 按长度降序排序，取第一条（最长的）
			longestFile = self.projectData + "/longest_contig.fa"
			cmd = f"seqkit sort -l -r {self.projectTerminalCtg} | seqkit head -n 1 -o {longestFile}"
			print(f"[CtgLinker] Running: {cmd}")
			result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
			
			if result.returncode == 0 and os.path.exists(longestFile) and os.path.getsize(longestFile) > 0:
				for gseq in SeqIO.parse(longestFile, 'fasta'):
					self.roundInputSeq = gseq
					break
			else:
				# 回退到 BioPython 方法
				print(f"[CtgLinker] seqkit failed, falling back to BioPython")
				for gseq in SeqIO.parse(self.projectTerminalCtg, 'fasta'):
					if len(gseq.seq) >= lenm:
						lenm = len(gseq.seq)
						self.roundInputSeq = gseq
		
		# ✨✨✨ 修复：检查是否找到可用的 seed ✨✨✨
		if self.roundInputSeq is None:
			print(f"[CtgLinker] No available contig found for seed selection in DG{self.projectID}")
			return  # 提前返回，让调用者处理
		
		# ✨✨✨ 修复：立即标记选中的seed为已使用 ✨✨✨
		if self.roundInputSeq.id not in self.ctgUsedID:
			self.ctgUsedID.append(self.roundInputSeq.id)
			print(f"[CtgLinker] Seed selected: {self.roundInputSeq.id} (marked as used)")
		
		ft=open(self.roundInputSeqFile,'w')
		l='>'+self.roundInputSeq.description+"\n"+str(self.roundInputSeq.seq)+"\n"
		ft.writelines(l)
		ft.close()
		des=self.roundInputSeq.description
		print (self.roundInputSeq.description,'des')
		des1=des.rstrip().split('\t')
		
		# Extract the base contig/scaffold ID for matching
		# Handle various ID formats: Contig-1, DG1, ExtensionSequence-DG1-Left, etc.
		base_id = des1[0]
		if base_id.startswith('ExtensionSequence-'):
			# Extract DG ID from ExtensionSequence-DG1-Left -> DG1
			base_id = base_id.replace('ExtensionSequence-', '')
			if '-Left' in base_id:
				base_id = base_id.replace('-Left', '')
			elif '-Right' in base_id:
				base_id = base_id.replace('-Right', '')
		
		ft=open(self.used,'r')
		rtagt=''
		ltagt=''
		for row in ft:
			if row.startswith('#'):
				continue
			row1=row.rstrip().split('\t')
			# Match by DG ID (first column) or tags (last column)
			# ✨ 修复：使用精确匹配而非子串匹配，避免 Contig-2 错误匹配到 Contig-22
			if len(row1) >= 4:
				# 将 tags 分割成列表进行精确匹配
				tags = row1[3].split(';')
				# 从每个 tag 中提取原始 contig ID（去除 -Right_xxx, -Left_xxx 等后缀）
				tag_ids = []
				for tag in tags:
					tag_id = tag
					if '-Right_' in tag:
						tag_id = tag.split('-Right_')[0]
					elif '-Left_' in tag:
						tag_id = tag.split('-Left_')[0]
					elif '-edge-' in tag:
						tag_id = tag.split('-edge-')[0]
					tag_ids.append(tag_id)
				
				if row1[0] == base_id or base_id in tag_ids:
					rtagt=row1[1]
					ltagt=row1[2]
					print (f"[CtgLinker] Found in used.txt: {row1}")
					print (f"  rtagt={rtagt}, ltagt={ltagt}")
					break
		ft.close()
		
		if len(des1)==1:
			# No tab in description, this is a fresh contig - extend both directions
			self.flaglist=['left','right']
			print (f"[CtgLinker] Fresh contig, extending both directions")
		else:
			# Has tab in description, check used.txt status
			self.flaglist=[]
			if rtagt == '' and ltagt == '':
				# Not found in used.txt, could be a new merged scaffold - extend both directions
				print (f"[CtgLinker] Not found in used.txt, treating as new scaffold")
				self.flaglist=['left','right']
			else:
				# Found in used.txt, check which directions are still available
				# Note: 
				# - '' (empty) means "can extend"
				# - '**' means "cannot extend (completed/failed/blocked)"
				# So '**' blocks extension, '' allows it
				if ltagt != '**':
					self.flaglist.append('left')
				if rtagt != '**':
					self.flaglist.append('right')
				print (f"[CtgLinker] Found in used.txt: rtagt='{rtagt}', ltagt='{ltagt}'")
				print (f"[CtgLinker] Available directions: {self.flaglist}")
				
				if len(self.flaglist) == 0:
					print (f"[CtgLinker] Info: Both directions marked as '**', no further extension")
					self.skipCurrentDG = True  # 标记跳过当前 DG
		
		print (f"[CtgLinker] Final flaglist: {self.flaglist}")
		
		# 使用 seqkit 从 terminalCtg.fa 中排除当前seed和已使用的contigs
		excludeIDs = set(self.ctgUsedID)
		excludeIDs.add(self.roundInputSeq.id)
		excludeIDFile = self.projectData + "/exclude_seed.txt"
		with open(excludeIDFile, 'w') as f:
			f.write('\n'.join(excludeIDs))
		
		tempFile = self.projectData + '/temp.fa'
		cmd = f"seqkit grep -v -f {excludeIDFile} {self.projectTerminalCtg} -o {tempFile}"
		print(f"[CtgLinker] Running: {cmd}")
		result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
		
		if result.returncode == 0:
			# 成功，替换原文件
			import shutil
			shutil.move(tempFile, self.projectTerminalCtg)
			# 获取剩余的 TerminalCtgID
			cmd_ids = f"seqkit seq -n {self.projectTerminalCtg}"
			result_ids = subprocess.run(cmd_ids, shell=True, capture_output=True, text=True)
			self.TerminalCtgID = [line.split()[0] for line in result_ids.stdout.strip().split('\n') if line]
		else:
			print(f"[CtgLinker] seqkit error: {result.stderr}, falling back to BioPython")
			# 回退到原始方法
			with open(tempFile, 'w') as ft:
				for gseq in SeqIO.parse(self.projectTerminalCtg, 'fasta'):
					if gseq.id != self.roundInputSeq.id and gseq.id not in self.ctgUsedID:
						ft.write(f'>{gseq.description}\n{gseq.seq}\n')
						self.TerminalCtgID.append(gseq.id)
			import shutil
			shutil.move(tempFile, self.projectTerminalCtg)

	def roundInit(self):
		self.projectOut=self.project+"/DG"+str(self.projectID)
		if not os.path.exists(self.projectOut):
			os.makedirs(self.projectOut)
		self.projectData=self.projectOut+"/data"
		if not os.path.exists(self.projectData):
			os.makedirs(self.projectData)
		self.projectTerminalCtg=self.projectOut+"/data/terminalCtg.fa"
		self.projectused=self.projectOut+"/DG"+str(self.projectID)+".used.txt"
		self.projectfasta=self.projectOut+"/DG"+str(self.projectID)+".fa"
		self.projectagppwd=self.projectOut+"/DG"+str(self.projectID)+".agp.path.txt"
		self.projectlog=self.projectOut+"/DG"+str(self.projectID)+".log"
		self.projectagp=self.projectOut+"/DG"+str(self.projectID)+".agp"
		
		
