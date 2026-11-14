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
import GapFillerClass
import subprocess
import tempfile
import time

class FindExtensionContigs(object):
	def __init__(self,ExtensionReads, data_type='hifi', ont_reads=None, original_reads_info=None):
		self.extensionReads=ExtensionReads
		self.data_type=data_type
		self.ont_reads=ont_reads
		self.original_reads_info=original_reads_info
		self.log=self.extensionReads.roundInput.elongation.roundDir+"/extensionConthgs.log"
		self.extensionSequence=self.extensionReads.roundInput.elongation.roundDir+"/extensionSequence."+self.extensionReads.roundInput.elongation.base.tag+".fa"
		self.extensionContigID=[]
		self.extensionLength=0

		# Initialize all attributes with default values to prevent AttributeError
		self.selectContigIdentity = 99.0
		self.selectContigDistance = 10
		self.selectContigAlnLength = 1000
		self.contigAlnMerge = False
		self.contigAlnMergeIdentity = 100.0
		self.selectExtensionContigsAln = []
		self.potentialExtensionContigsAln = ""
		self.potentialExtensionContigsAlnDict = {}
		self.maxextensionLen = 0
		self.FuzzyAln = []
		self.selectContigNote = ""
		self.extensionSeqNote = ""
		self.readCommonResult = ""
		self.hifiasmResultDict = {}
		self.extensionContigs = ""

		if os.path.exists(self.extensionSequence)==True and os.path.getsize(self.extensionSequence)!=0:
			self.readlog()
		else:
			logfilet=open(self.log,'w')

			self.hifiasm()

			# Check if hifiasm attributes were properly initialized
			hifiasm_command = getattr(self, 'hifiasmCommand', 'Not initialized (skipped due to no extension reads)')
			hifiasm_dir = getattr(self, 'hifiasmDir', 'Not initialized')
			hifiasm_result = getattr(self, 'hifiasmResult', 'Not initialized')

			logLine='hifiasmCommand\t'+hifiasm_command+"\n"
			logLine+='hifiasmDir\t'+hifiasm_dir+"\n"
			logLine+='hifiasmResult\t'+hifiasm_result+"\n"
			listt=[]
			for k,v in self.hifiasmResultDict.items():
				l=k+";"+';'.join(v)
				listt.append(l)
			logLine+='hifiasmResultDict\t'+':'.join(listt)+"\n"

			if os.path.exists(self.hifiasmResult)==True and os.path.getsize(self.hifiasmResult)!=0:
				self.extensionSeqNote='hifiasm'
				self.readCommonResult='None'
				self.extensionContigs=self.hifiasmResult
			else:
				self.readCommon()
				self.extensionContigs=self.readCommonResult
			logLine+='extensionSeqNote\t'+self.extensionSeqNote+"\n"
			logLine+='readCommonResult\t'+self.readCommonResult+"\n"
			logLine+='extensionContigs\t'+self.extensionContigs+"\n"
			self.selectContigNote=''
			self.selectContigNote=self.selectContig()
			if 'hifiasmHasNoAccurateAssembly' in self.selectContigNote:
				print (self.selectContigNote)
				self.readCommon()
				self.extensionContigs=self.readCommonResult
				self.selectContigNote=self.selectContig()
				if len(self.selectExtensionContigsAln)==0:
					self.selectContigNote+='No extension contigs or reads found\n'
				logLine+='selectContigNote\t'+self.selectContigNote+"\n"

			logLine+='potentialExtensionContigsAln\t'+self.potentialExtensionContigsAln+"\n"
			logLine+='selectContigIdentity\t'+str(self.selectContigIdentity)+"\n"
			logLine+='selectContigDistance\t'+str(self.selectContigDistance)+"\n"
			logLine+='selectContigAlnLength\t'+str(self.selectContigAlnLength)+"\n"
			logLine+='contigAlnMerge\t'+str(self.contigAlnMerge)+"\n"
			logLine+='contigAlnMergeIdentity\t'+str(self.contigAlnMergeIdentity)+"\n"
			logtmp=''
			for k,v in self.potentialExtensionContigsAlnDict.items():
				listRefForward,listQueryForward,listRefReverse,listQueryReverse,qlen=v
				l=k+"-"
				for i in listRefForward:
					s,e=i
					lt=str(s)+","+str(e)+";"
					l+=lt
				l+="-"
				for i in listQueryForward:
					s,e=i
					lt=str(s)+","+str(e)+";"
					l+=lt
				l+="-"
				for i in listRefReverse:
					s,e=i
					lt=str(s)+","+str(e)+";"
					l+=lt
				l+='-'
				for i in listQueryReverse:
					s,e=i
					lt=str(s)+","+str(e)+";"
					l+=lt
				l+='-'+str(qlen)+"\t"
				logtmp+=l
			logLine+='potentialExtensionContigsAlnDict\t'+logtmp+"\n"

			logtmp=''
			for i in self.selectExtensionContigsAln:
				r,el=i
				l=r.rstrip()+"-"+str(el)+";"
				logtmp+=l
			logLine+='selectExtensionContigsAln\t'+logtmp+"\n"
			logLine+='maxextensionLen\t'+str(self.maxextensionLen)+"\n"
			logLine+='selectContigNote\t'+self.selectContigNote+"\n"
			logtmp=''
			for i in self.FuzzyAln:
				l=i[0].rstrip()+'-'+str(i[1])+";"
				logtmp+=l
			logLine+='FuzzyAln\t'+logtmp+"\n"
			logLine+='extensionContigID\t'+";".join(self.extensionContigID)+"\n"
			logLine+='extensionLength\t'+str(self.extensionLength)+"\n"
			logLine+='extensionSequence\t'+self.extensionSequence+"\n"
			logfilet.writelines(logLine)
			logfilet.close()

	def selectContig(self):
		self.potentialExtensionContigsAln=self.extensionReads.roundInput.elongation.roundDir+"/potentialExtensionContigs.asm."+self.extensionReads.roundInput.elongation.base.tag+"seq.mummer"

		# Check if extension contigs file exists and is not empty
		if not os.path.exists(self.extensionContigs) or os.path.getsize(self.extensionContigs) == 0:
			print(f"Warning: Extension contigs file does not exist or is empty: {self.extensionContigs}")
			print("Skipping mummer analysis and setting termination condition")
			# Set proper termination condition instead of creating empty files
			self.selectExtensionContigsAln = []
			return "No extension contigs or reads found"

		self.potentialExtensionContigsAln=GapFillerClass.mummer(self.extensionReads.roundInput.inputSeq,self.extensionContigs,self.potentialExtensionContigsAln)
		self.selectContigIdentity=99.0
		self.selectContigDistance=10
		self.selectContigAlnLength=1000
		self.contigAlnMerge=False
		self.contigAlnMergeIdentity=100.0

		self.contigAlnFilter(self.selectContigIdentity)

		while len(self.selectExtensionContigsAln)<=0:
			if self.selectContigAlnLength<=500:
				if self.selectContigIdentity<95.0:
					if self.selectContigDistance>self.extensionReads.roundInput.elongation.base.edge or self.selectContigDistance>self.maxextensionLen:
						self.contigAlnMerge=True		
					else:
						self.selectContigDistance+=10
				else:
					self.selectContigIdentity-=1.0
			else:
				self.selectContigAlnLength-=100
			if self.contigAlnMerge==False:
				self.contigAlnFilter(self.selectContigIdentity)
			else:
				break

		if self.contigAlnMerge==True:
			self.selectContigNote+='FuzzyAlignments\n'
			self.selectContigDistance=10
			while len(self.selectExtensionContigsAln)<=0 and self.contigAlnMergeIdentity>=80.0 and self.selectContigDistance<=self.extensionReads.roundInput.elongation.base.edge:
				self.potentialExtensionContigsAln=self.extensionReads.roundInput.elongation.roundDir+"/potentialExtensionContigs.asm."+self.extensionReads.roundInput.elongation.base.tag+"seq.mummer.delta.filter.coords"
				if self.contigAlnMergeIdentity<=80.0:
					if self.selectContigDistance<=self.extensionReads.roundInput.elongation.base.edge:
						self.selectContigDistance+=10
				else:
					self.contigAlnMergeIdentity-=1.0
					print (self.contigAlnMergeIdentity)
				self.contigAlnFilter(self.contigAlnMergeIdentity)
				self.FuzzyAln=self.mergeContig()
				print (self.FuzzyAln)
				self.selectExtensionContigsAln=self.FuzzyAln
				
				#self.contigAlnFilter(self.contigAlnMergeIdentity)
				
			if len(self.selectExtensionContigsAln)<=0 and self.contigAlnMergeIdentity<=80.0:
				self.selectContigNote+='hifiasmHasNoAccurateAssembly Use readsCommonSequence\n'
				return self.selectContigNote
		else:
			self.selectContigNote+='SolidAlignments\n'
			self.FuzzyAln=[]

		if len(self.selectExtensionContigsAln)>1:
			asm=[]
			self.selectContigNote+="\t\tFind maximum identity alignment"
			for i in self.selectExtensionContigsAln:
				aln,mlen=i
				if asm==[]:
					asm.append(i)
				else:
					ia=asm[0][0].rstrip().split('\t')[6]
					i1=aln.rstrip().split('\t')[6]
					if float(i1)>float(ia):
						asm=[]
						asm.append(i)
					elif float(i1)==float(ia):
						asm.append(i)
			if asm[0][0].rstrip().split('\t')[6]==0 or len(asm)!=1:
				self.selectContigNote+="\t\tFind maximum length alignment\n"
				asm1=[]
				for i in asm:
					aln,mlen=i
					if asm1==[]:
						asm1.append(i)
					else:
						if asm1[0][1]<mlen:
							asm1=[]
							asm1.append(i)
			else:
				asm1=asm
			self.selectExtensionContigsAln=asm1
		file1=open(self.extensionSequence,'w')
		for i in self.selectExtensionContigsAln:
			aln,mlen=i
			outseq,extensionseq,noseq,note1,name1,name2=self.extensionSeq(aln)
			l='>ExtensionSequence-'+self.extensionReads.roundInput.elongation.base.name+"\t"+self.extensionReads.roundInput.inputSeedSequence.id+"\t"+name1+"\n"+outseq+"\n"
			file1.writelines(l)
			self.selectContigNote+=note1
			self.extensionContigID=self.extensionContigID+name2
			ext_len = len(outseq) - len(self.extensionReads.roundInput.inputSeedSequence.seq)
			if ext_len < 0:
				# Guard against negative extension due to reverse/edge-case alignment
				self.selectContigNote += '\nselectContigNote\tNegative extension length corrected from ' + str(ext_len) + ' to 0\n'
				ext_len = 0
			self.extensionLength = ext_len
		file1.close()
		return self.selectContigNote

	def extensionSeq(self,row):
		seqtseq=self.extensionReads.roundInput.inputSeedSequence
		row1=row.rstrip().split('\t')
		a,b,c,d=int(row1[0]),int(row1[1]),int(row1[2]),int(row1[3])
		e,f=int(row1[4]),int(row1[5])
		name1=row1[-1]
		name2=name1.split('-ovl-')
		list0=[]
		flag=self.extensionReads.roundInput.elongation.base.flag
		note1="selectContigNote\tExtension: "+name1+"\n"
		for gseq in SeqIO.parse(self.extensionContigs,'fasta'):
			if gseq.id==name1:
				if flag!='left':
					if d>=int(row1[8])-10:
						extensionseq=gseq.seq[:c-1]
						note1=note1+'selectContigNote\tExtensionseq alignment:'+row
					else:
						extensionseq1=gseq.seq.reverse_complement()
						nend=len(gseq.seq)-c
						note1=note1+'selectContigNote\tExtensionseq alignment reverse:'+row
						extensionseq=extensionseq1[:nend]
				else:
					if c<=10:
						extensionseq=gseq.seq[d:]
						note1=note1+'selectContigNote\tExtensionseq alignment:'+row
					else:
						extensionseq1=gseq.seq.reverse_complement()
						nstart=len(gseq.seq)-d+1
						extensionseq=extensionseq1[nstart:]
						note1=note1+'selectContigNote\tExtensionseq alignment reverse:'+row
		if flag!='left':
			noseq=seqtseq.seq[int(row1[0])-1:]
			note1=note1+'selectContigNote\t\tSeedsequence length: '+str(len(seqtseq.seq))+"\nselectContigNote\t\tExtensionlength: "+str(len(extensionseq))+"\n"
			outseq=extensionseq+noseq
		else:
			noseq=seqtseq.seq[:int(row1[1])]
			note1=note1+'selectContigNote\t\tSeedsequence length: '+str(len(seqtseq.seq))+"\nselectContigNote\t\tExtensionlength: "+str(len(extensionseq))+"\n"
			outseq=noseq+extensionseq
		note1=note1+'selectContigNote\t\tTotalLength: '+str(len(outseq))
		return outseq,extensionseq,noseq,note1,name1,name2

	def merge(self,list1):
		list2=sorted(list1,key=lambda x:x[0])
		j=0
		while j<len(list2):
			j1=j+1
			while j1<len(list2):
				a,b=list2[j]
				c,d=list2[j1]
				x=range(a,b+1,1)
				y=range(c,d+1,1)
				t1=sorted(list(set(x)&set(y)))
				if len(t1)!=0:
					t2=sorted(list(set(x)|set(y)))
					list2[j]=[t2[0],t2[-1]]
					list2.pop(j1)
					j1-=1
				j1+=1
			j+=1
		list3=[]
		listLen=0
		for i in list2:
			s,e=i
			if s!=e:
				list3.append(i)
				listLen=listLen+(e-s+1)
		return list3,listLen

	def mergeContig(self):
		FuzzyAln=[]
		for k,v in self.potentialExtensionContigsAlnDict.items():
			listRefForward,listQueryForward,listRefReverse,listQueryReverse,QueryLen=v
			refAalnmergeForward,refAlnmergeForwardLen=self.merge(listRefForward)
			refAalnmergeReverse,refAlnmergeReverseLen=self.merge(listRefReverse)
			if refAlnmergeForwardLen>refAlnmergeReverseLen:
				refaln=listRefForward
				queryaln=listQueryForward
				tag='f'
			else:
				refaln=listRefReverse
				queryaln=listQueryReverse
				tag='r'
			refalnmerge,refalnlen=self.merge(refaln)
			if len(refalnmerge)!=1:
				effectiveQueryAln=[]
				effectiveRefAln=[]
				if self.extensionReads.roundInput.elongation.base.flag!='left':
					effectiveRefEdgeAln=refalnmerge[0]
				else:
					effectiveRefEdgeAln=refalnmerge[-1]
				j=0
				s,e=effectiveRefEdgeAln
				while j<len(refaln):
					s1,e1=refaln[j]
					if s1>=s and e1<=e:
						effectiveQueryAln.append(queryaln[j])
					j+=1
				effectiveRefAln=[effectiveRefEdgeAln]
				queryaln=effectiveQueryAln
			else:
				effectiveRefAln=refalnmerge
			queryalnmerge,queryalnlen=self.merge(queryaln)
			effectiveQueryAln=queryalnmerge
			
			refFuzzyAln=[]
			for i in effectiveRefAln:
				s1,e1=i
				if self.extensionReads.roundInput.elongation.base.flag!='left':
					if s1==1:
						refFuzzyAln.append(i)
				else:
					if e1==len(self.extensionReads.roundInput.inputSeedSequence.seq):
						refFuzzyAln.append(i)
			queryFuzzyAln=[]
			for i in effectiveQueryAln:
				s1,e1=i
				if self.extensionReads.roundInput.elongation.base.flag!='left':
					if e1==QueryLen:
						queryFuzzyAln.append(i)
				else:
					if s1==1:
						queryFuzzyAln.append(i)
			if refFuzzyAln!=[] and queryFuzzyAln!=[]:
				for i in refFuzzyAln:
					am,bm=i
					for i1 in queryFuzzyAln:
						cm,dm=i1
						em=bm-am
						if tag=='f':
							fm=dm-cm+1
							lit=[str(am),str(bm),str(cm),str(dm),str(em),str(fm),str(self.contigAlnMergeIdentity),str(0),str(QueryLen),str(0),str(0),str(0),str(k)]
							lit='\t'.join(lit)+'\n'
						else:
							fm=dm-cm+1
							lit=[str(am),str(bm),str(dm),str(cm),str(em),str(fm),str(self.contigAlnMergeIdentity),str(0),str(QueryLen),str(0),str(0),str(0),str(k)]
							lit='\t'.join(lit)+'\n'
						FuzzyAln.append([lit,max(em,fm)])
			else:
				am=effectiveRefAln[0][0]
				bm=effectiveRefAln[-1][1]
				cm=effectiveQueryAln[0][0]
				dm=effectiveQueryAln[-1][1]
				em=bm-am
				if tag=='f':
					fm=dm-cm+1
					lit=[str(am),str(bm),str(cm),str(dm),str(em),str(fm),str(self.contigAlnMergeIdentity),str(0),str(QueryLen),str(0),str(0),str(0),str(k)]
					lit='\t'.join(lit)+'\n'
				else:
					fm=dm-cm+1
					lit=[str(am),str(bm),str(dm),str(cm),str(em),str(fm),str(self.contigAlnMergeIdentity),str(0),str(QueryLen),str(0),str(0),str(0),str(k)]
					lit='\t'.join(lit)+'\n'
				if fm < QueryLen:
					if refFuzzyAln!=[] or queryFuzzyAln!=[]:
						FuzzyAln.append([lit,max(em,fm)])
		self.potentialExtensionContigsAln=self.extensionReads.roundInput.elongation.roundDir+"/potentialExtensionContigs.asm.FuzzyAln.delta.filter.coords"
		file1=open(self.potentialExtensionContigsAln,'w')
		for i in FuzzyAln:
			i1,i2=i
			file1.writelines(i1)
		file1.close()
		return FuzzyAln

	def contigAlnFilter(self,selectIdentity):
		file1=open(self.potentialExtensionContigsAln,'r')
		self.potentialExtensionContigsAlnDict={}
		self.selectExtensionContigsAln=[]
		self.maxextensionLen=0
		for row in file1:
			row1=row.rstrip().split('\t')
			s1,e1,s2,e2=int(row1[0]),int(row1[1]),int(row1[2]),int(row1[3])
			if self.extensionReads.roundInput.elongation.base.flag!='left':
				refDistance=s1-1
				if e2>=s2:
					extensionLen=s2-1
					queryDistance=int(row1[8])-e2
				else:
					extensionLen=int(row1[8])-s2
					queryDistance=e2-1
			else:
				refDistance=int(row1[7])-e1
				if s2<e2:
					extensionLen=int(row1[8])-e2
					queryDistance=s2-1
				else:
					extensionLen=e2-1
					queryDistance=int(row1[8])-s2

			if float(row1[6])>=selectIdentity:
				if row1[12] in self.potentialExtensionContigsAlnDict:
					listRefForward,listQueryForward,listRefReverse,listQueryReverse,Querylen=self.potentialExtensionContigsAlnDict[row1[12]]
				else:
					listRefForward=[]
					listQueryForward=[]
					listRefReverse=[]
					listQueryReverse=[]
				if e2>=s2:
					listRefForward.append([s1,e1])
					listQueryForward.append([s2,e2])
				else:
					listRefReverse.append([s1,e1])
					listQueryReverse.append([e2,s2])
				self.potentialExtensionContigsAlnDict[row1[12]]=[listRefForward,listQueryForward,listRefReverse,listQueryReverse,int(row1[8])]
				if extensionLen>self.maxextensionLen:
					self.maxextensionLen=extensionLen
				if queryDistance<=self.selectContigDistance and refDistance<=self.selectContigDistance:
					maxAlnLen=max([int(row1[4]),int(row1[5])])
					if maxAlnLen>=self.selectContigAlnLength and extensionLen>=0:
						self.selectExtensionContigsAln.append([row,extensionLen])
		file1.close()

	def readCommon(self):
		self.readCommonResult=self.extensionReads.roundInput.elongation.roundDir+"/readsCommonSequence.fasta"

		# For mixed mode, combine HiFi and ONT extension reads for readsCommon
		if self.data_type == 'mixed' and hasattr(self.extensionReads, 'ont_extensionReads'):
			# readsCommon 需要合并 HiFi 和 ONT reads 到单个文件
			combined_extension_reads = self.combineExtensionReadsForReadsCommon()
			if combined_extension_reads:
				extension_reads_file = combined_extension_reads
			else:
				print("Warning: Failed to combine extension reads for mixed mode")
				extension_reads_file = self.extensionReads.extensionReads
		else:
			extension_reads_file = self.extensionReads.extensionReads

		# Check if extension reads file exists
		if extension_reads_file is None or not os.path.exists(extension_reads_file):
			print("Warning: No extension reads file available for readsCommon analysis")
			print("Skipping readsCommon analysis and setting empty results")
			# Set results to trigger proper termination condition
			self.selectContigNote = "No extension contigs or reads found"
			self.extensionSeqNote = "No extension reads found for readsCommon analysis"
			# Don't create empty file - let the system handle termination properly
			return

		# ========== 恢复 v1 的预过滤逻辑 ==========
		# 第一步：使用 MUMmer 比对种子序列与所有延伸reads，进行预过滤
		# 这样可以显著减少后续两两比对的次数，提升性能
		print("Performing pre-filtering with MUMmer (seed sequence vs extension reads)...")
		
		# 获取种子序列文件路径
		seed_seq_file = self.extensionReads.roundInput.inputSeq
		
		# 使用 MUMmer 进行预过滤比对
		prefilter_mummerout = GapFillerClass.mummer(
			seed_seq_file,
			extension_reads_file,
			self.extensionReads.roundInput.elongation.roundDir+'/temp3_prefilter'
		)
		
		# 第二步：从 MUMmer 结果中提取通过预过滤的 reads ID
		readlisttemp = []
		try:
			ft3 = open(prefilter_mummerout, 'r')
			for r in ft3:
				r1 = r.rstrip().split('\t')
				if len(r1) > 0 and r1[-1] not in readlisttemp:
					readlisttemp.append(r1[-1])  # 只保留与种子序列有比对的 read ID
			ft3.close()
			print(f"Pre-filtering complete: {len(readlisttemp)} reads passed (aligned with seed sequence)")
			
			# 清理预过滤临时文件
			import glob
			for temp_file in glob.glob(self.extensionReads.roundInput.elongation.roundDir+'/temp3_prefilter*'):
				try:
					os.remove(temp_file)
				except:
					pass
					
		except Exception as e:
			print(f"Error during pre-filtering: {e}")
			print("Falling back to using all extension reads (no pre-filtering)")
			# 如果预过滤失败，回退到使用所有 reads
			readlisttemp = []
			try:
				for record in SeqIO.parse(extension_reads_file, 'fasta'):
					if record.id not in readlisttemp:
						readlisttemp.append(record.id)
			except Exception as e2:
				print(f"Error reading extension reads file: {e2}")
				readlisttemp = []
		file1=open(self.readCommonResult,'w')

		# Count total extension reads (HiFi + ONT for mixed mode)
		# Check if extensionReadsNum attribute exists, if not set it to 0
		if hasattr(self.extensionReads, 'extensionReadsNum'):
			total_extension_reads = self.extensionReads.extensionReadsNum
		else:
			print("Warning: extensionReadsNum attribute not found, setting to 0")
			total_extension_reads = 0

		if self.data_type == 'mixed' and hasattr(self.extensionReads, 'ont_extensionReadsNum'):
			total_extension_reads += getattr(self.extensionReads, 'ont_extensionReadsNum', 0)

		if total_extension_reads > 1:
			self.extensionSeqNote='readsCommon'
			
			# ========== 方案1：使用 minimap2 all-vs-all 模式 ==========
			print(f"Using minimap2 all-vs-all mode for overlap detection ({len(readlisttemp)} reads)...")
			
			# 创建只包含预过滤后 reads 的临时文件
			filtered_reads_file = self.extensionReads.roundInput.elongation.roundDir+'/filtered_reads.fa'
			
			# 第一步：写入过滤后的reads到文件
			filtered_count = 0
			with open(filtered_reads_file, 'w') as f_filtered:
				for gseq in SeqIO.parse(extension_reads_file, 'fasta'):
					if gseq.id in readlisttemp:
						f_filtered.write(f">{gseq.id}\n{gseq.seq}\n")
						filtered_count += 1
			
			print(f"Created filtered reads file with {filtered_count} reads")
			
			# 第二步：使用SeqIO.index创建索引（内存友好，按需读取）
			# 这样不会把所有序列加载到内存，只在需要时读取
			print("Creating sequence index (memory-efficient)...")
			reads_dict = SeqIO.index(filtered_reads_file, "fasta")
			print(f"Sequence index created for {len(reads_dict)} reads")
			
			# 根据数据类型选择 minimap2 预设
			if self.data_type == 'ont':
				minimap2_preset = 'ava-ont'
			else:
				minimap2_preset = 'ava-pb'  # HiFi 和 mixed 模式
			
			# 运行 minimap2 all-vs-all 比对
			# 使用 -N 1 参数：每个query只保留最优比对，大幅减少PAF文件大小
			paf_output = self.extensionReads.roundInput.elongation.roundDir+'/all_vs_all.paf'
			thread_num = self.extensionReads.roundInput.elongation.base.thread
			
			minimap2_cmd = f"minimap2 -x {minimap2_preset} -N 1 -t {thread_num} {filtered_reads_file} {filtered_reads_file} > {paf_output}"
			
			print(f"Running minimap2 all-vs-all with -N 1: {minimap2_cmd}")
			
			try:
				result = subprocess.run(minimap2_cmd, shell=True, capture_output=True, text=True)
				if result.returncode != 0:
					print(f"Warning: minimap2 failed: {result.stderr}")
					raise Exception("minimap2 all-vs-all failed")
				
				print(f"minimap2 completed, parsing PAF file...")
				
				# 简化的解析逻辑：minimap2 -N 1 已经保证每个query只有最优比对
				# 这里只需要：① 去重A-B/B-A  ② 边缘过滤  ③ 长度过滤
				overlap_dict = {}  # {pair_key: coord_info}
				
				print("Parsing PAF and filtering (edge alignment + length)...")
				with open(paf_output, 'r') as paf:
					for line in paf:
						if line.startswith('#'):
							continue
						
						fields = line.strip().split('\t')
						if len(fields) < 12:
							continue
						
						# PAF 格式字段
						query_name = fields[0]
						query_len = int(fields[1])
						query_start = int(fields[2])
						query_end = int(fields[3])
						strand = fields[4]
						target_name = fields[5]
						target_len = int(fields[6])
						target_start = int(fields[7])
						target_end = int(fields[8])
						num_matches = int(fields[9])
						aln_block_len = int(fields[10])
						mapq = int(fields[11])
						
						# 跳过自己比对自己
						if query_name == target_name:
							continue
						
						# 去重：A-B和B-A只保留一个
						pair_key = tuple(sorted([query_name, target_name]))
						if pair_key in overlap_dict:
							continue  # 已经处理过这对reads
						
						# 筛选条件1：边缘比对（使用v1的严格策略）
						# v1策略：比对必须精确在序列边缘（起始位置=0或结束位置=长度）
						# 注意：PAF是0-based，所以起始=0表示序列开头
						query_at_edge = (query_start == 0 or query_end == query_len)
						target_at_edge = (target_start == 0 or target_end == target_len)
						
						# v1要求：query和target都必须在边缘
						if not (query_at_edge and target_at_edge):
							continue  # 不满足严格边缘条件，跳过
						
						# 计算overlap长度（用于后续记录）
						overlap_len = min(query_end - query_start, target_end - target_start)
						
						# 注意：v1没有明确的长度阈值，这里也不设置
						# 如果需要过滤短overlap，可以取消下面的注释：
						# if overlap_len < 1000:
						#     continue
						
						# 检查reads是否存在
						try:
							if query_name not in reads_dict or target_name not in reads_dict:
								continue
						except:
							continue
						
						# 保存坐标信息（通过所有筛选条件）
						coord_info = (query_name, query_start, query_end, query_len,
						             target_name, target_start, target_end, target_len,
						             overlap_len, mapq)
						overlap_dict[pair_key] = coord_info
				
				print(f"Filtering complete: {len(overlap_dict)} valid overlaps (edge + length ≥1000bp)")
				print("Phase 2: Extracting sequences for best alignments...")
				
				# 第二阶段：只对最优结果提取序列并写入
				overlap_count = 0
				for pair_key, coord_info in overlap_dict.items():
					(query_name, query_start, query_end, query_len,
					 target_name, target_start, target_end, target_len,
					 overlap_len, mapq) = coord_info
					
					# 从索引中按需获取序列（内存友好）
					query_seq = str(reads_dict[query_name].seq)
					target_seq = str(reads_dict[target_name].seq)
					
					# 根据比对位置提取序列
					# 选择较长的比对区域作为共有序列
					if query_end - query_start > target_end - target_start:
						common_seq = query_seq[query_start:query_end]
					else:
						common_seq = target_seq[target_start:target_end]
					
					# 写入结果
					paf_info = f"PAF:q={query_start}-{query_end},t={target_start}-{target_end},len={overlap_len},mapq={mapq}"
					output_line = f">{query_name}-ovl-{target_name}\tcommon-{len(common_seq)}\t{paf_info}\n{common_seq}\n"
					file1.write(output_line)
					overlap_count += 1
				
				# 关闭索引文件
				reads_dict.close()
				
				print(f"minimap2 all-vs-all completed: found {overlap_count} valid overlaps")
				
				# 清理临时文件
				try:
					os.remove(filtered_reads_file)
					os.remove(paf_output)
				except:
					pass
				
			except Exception as e:
				print(f"Error during minimap2 all-vs-all: {e}")
				print("Falling back to original MUMmer-based pairwise comparison...")
				
				# 回退到原始的 MUMmer 两两比对方法
				listCommon=[]
				j=1
				for gseq1 in SeqIO.parse(extension_reads_file,'fasta'):
					if gseq1.id not in readlisttemp:
						continue
					ft1=open(self.extensionReads.roundInput.elongation.roundDir+'/temp1','w')
					l='>'+gseq1.id+'\n'+gseq1.seq+"\n"
					ft1.writelines(l)
					ft1.close()
					readSeq1=gseq1.seq
					listCommon.append(gseq1.id)

					for gseq2 in SeqIO.parse(extension_reads_file,'fasta'):
						if gseq2.id not in readlisttemp:
							continue
						if gseq1.id != gseq2.id:
							if gseq2.id in listCommon:
								continue
							else:
								j=j+1
								ft2=open(self.extensionReads.roundInput.elongation.roundDir+'/temp2','w')
								readSeq2=gseq2.seq
								l='>'+gseq2.id+'\n'+gseq2.seq+"\n"
								ft2.writelines(l)
								ft2.close()

								mummerout=GapFillerClass.mummer(self.extensionReads.roundInput.elongation.roundDir+'/temp2',self.extensionReads.roundInput.elongation.roundDir+'/temp1',self.extensionReads.roundInput.elongation.roundDir+'/temp3')
								ft3=open(mummerout,'r')
								maxCommonLen=0
								mummeresult=[]
								for r in ft3:
									r1=r.rstrip().split('\t')
									if int(r1[0])==1 or int(r1[0])==int(r1[7]) or int(r1[1])==1 or int(r1[1])==int(r1[7]):
								
										if int(r1[2])==1 or int(r1[2])==int(r1[8]) or int(r1[3])==1 or int(r1[3])==int(r1[8]):
											maxAlnlen=max(float(r1[5]),float(r1[4]))
											if maxAlnlen>=maxCommonLen:
												maxCommonLen=maxAlnlen
												mummeresult=r1
								ft3.close()

								if mummeresult!=[]:
									if int(mummeresult[4])>int(mummeresult[5]):
										seq1=readSeq2[int(mummeresult[0])-1:int(mummeresult[1])]
									else:
										if int(mummeresult[2])<int(mummeresult[3]):
											seq1=readSeq1[int(mummeresult[2])-1:int(mummeresult[3])]
										else:
											seq1=readSeq1[int(mummeresult[3])-1:int(mummeresult[2])]
									l='>'+gseq1.id+"-ovl-"+gseq2.id+"\tcommon-"+str(len(seq1))+'\t'+r+seq1+"\n"
									file1.writelines(l)
								commendline='rm '+self.extensionReads.roundInput.elongation.roundDir+'/temp2'
								os.system(commendline)
								commendline='rm '+self.extensionReads.roundInput.elongation.roundDir+'/temp3*'
								os.system(commendline)
					commendline='rm '+self.extensionReads.roundInput.elongation.roundDir+'/temp1'
					os.system(commendline)
		else:
			self.extensionSeqNote='onlyOneRead'
			for gseq in SeqIO.parse(self.extensionReads.extensionReads,'fasta'):
				l='>'+gseq.id+"\n"+gseq.seq+"\n"
				file1.writelines(l)
		file1.close()

	def prepareHifiasmReads(self):
		"""
		为hifiasm准备正确格式的筛选后FASTQ文件
		将extension reads FASTA转换为FASTQ，从原始FASTQ中恢复质量信息
		根据混合模式状态决定使用哪些reads
		混合模式只处理两种情况：hifi_only 或 ont_only
		"""
		# 检查混合模式状态
		mixed_mode_status = getattr(self.extensionReads, 'mixed_mode_status', None)

		if mixed_mode_status == 'both_failed':
			print("混合模式：HiFi和ONT都失败，无法准备hifiasm reads")
			return None
		elif mixed_mode_status == 'ont_only':
			print("混合模式：只有ONT成功，使用ONT reads进行hifiasm")
			return self._prepareONTOnlyReads()
		elif mixed_mode_status == 'hifi_only':
			print("混合模式：只有HiFi成功，使用HiFi reads进行hifiasm")
			return self._prepareHiFiOnlyReads()
		else:
			# 非混合模式或未设置状态，使用原有逻辑
			return self._prepareHiFiOnlyReads()

	def _prepareHiFiOnlyReads(self):
		"""准备HiFi reads用于hifiasm"""
		# Check if extension reads exist
		if not hasattr(self.extensionReads, 'extensionReads') or self.extensionReads.extensionReads is None:
			print("Warning: No HiFi extension reads available for hifiasm preparation")
			return None

		# HiFi extension reads FASTA → FASTQ
		hifi_extension_fasta = self.extensionReads.extensionReads

		# Check if the extension reads file exists
		if not os.path.exists(hifi_extension_fasta):
			print(f"Warning: Extension reads file does not exist: {hifi_extension_fasta}")
			return None

		# 禁用FA→FQ转换，直接使用FASTA文件
		# hifi_extension_fastq = hifi_extension_fasta.replace('.fa', '.fq')
		# 
		# # 简化逻辑：根据 processed_reads/hifi_reads.fq 是否存在来决定
		# # - 存在 .fq → 原始输入是FASTQ → 执行FA→FQ转换
		# # - 不存在 .fq → 原始输入是FASTA → 直接使用FASTA
		# # 理由：DEGAP.py预处理阶段已经明确区分了格式
		# #   - FASTQ输入会创建 processed_reads/*.fq 软链接
		# #   - FASTA输入只创建 processed_reads/*.fa
		# 
		# out_dir = self.extensionReads.roundInput.elongation.base.out
		# processed_hifi_fq = os.path.join(out_dir, "processed_reads", "hifi_reads.fq")
		# 
		# if os.path.exists(processed_hifi_fq):
		# 	# 原始输入是FASTQ格式 → 需要转换extension reads为FASTQ
		# 	print(f"Detected original HiFi input is FASTQ (found {processed_hifi_fq})")
		# 	print(f"Converting HiFi extension reads to FASTQ: {hifi_extension_fasta} → {hifi_extension_fastq}")
		# 	
		# 	hifi_fastq_result = self._convert_extension_fasta_to_fastq(
		# 		hifi_extension_fasta,
		# 		processed_hifi_fq,
		# 		hifi_extension_fastq
		# 	)
		# 	
		# 	if hifi_fastq_result:
		# 		print(f"✅ HiFi extension FASTQ ready: {hifi_fastq_result}")
		# 		return hifi_fastq_result
		# 	else:
		# 		print("⚠️ Failed to convert HiFi extension reads to FASTQ, using FASTA fallback")
		# 		return hifi_extension_fasta
		# else:
		# 	# 原始输入是FASTA格式 → 直接使用FASTA
		# 	print(f"Detected original HiFi input is FASTA (no .fq file in processed_reads/)")
		# 	print(f"Using FASTA directly for hifiasm: {hifi_extension_fasta}")
		# 	return hifi_extension_fasta
		
		# 直接使用FASTA文件，不进行FA→FQ转换
		print(f"Using FASTA directly for hifiasm (FA→FQ conversion disabled): {hifi_extension_fasta}")
		return hifi_extension_fasta

	def _prepareONTOnlyReads(self):
		"""准备ONT reads用于hifiasm"""
		if not hasattr(self.extensionReads, 'ont_extensionReads'):
			print("Warning: No ONT extension reads available")
			return None

		ont_extension_fasta = self.extensionReads.ont_extensionReads
		if not os.path.exists(ont_extension_fasta):
			print(f"Warning: ONT extension reads file does not exist: {ont_extension_fasta}")
			return None

		# 禁用FA→FQ转换，直接使用FASTA文件
		# ont_extension_fastq = ont_extension_fasta.replace('.fa', '.fq')
		# 
		# # 简化逻辑：根据 processed_reads/ont_reads.fq 是否存在来决定
		# # - 存在 .fq → 原始输入是FASTQ → 执行FA→FQ转换
		# # - 不存在 .fq → 原始输入是FASTA → 直接使用FASTA
		# # 理由：DEGAP.py预处理阶段已经明确区分了格式
		# 
		# out_dir = self.extensionReads.roundInput.elongation.base.out
		# processed_ont_fq = os.path.join(out_dir, "processed_reads", "ont_reads.fq")
		# 
		# if os.path.exists(processed_ont_fq):
		# 	# 原始输入是FASTQ格式 → 需要转换extension reads为FASTQ
		# 	print(f"Detected original ONT input is FASTQ (found {processed_ont_fq})")
		# 	print(f"Converting ONT extension reads to FASTQ: {ont_extension_fasta} → {ont_extension_fastq}")
		# 	
		# 	ont_fastq_result = self._convert_extension_fasta_to_fastq(
		# 		ont_extension_fasta,
		# 		processed_ont_fq,
		# 		ont_extension_fastq
		# 	)
		# 	
		# 	if ont_fastq_result:
		# 		print(f"✅ ONT extension FASTQ ready: {ont_fastq_result}")
		# 		return ont_fastq_result
		# 	else:
		# 		print("⚠️ Failed to convert ONT extension reads to FASTQ, using FASTA fallback")
		# 		return ont_extension_fasta
		# else:
		# 	# 原始输入是FASTA格式 → 直接使用FASTA
		# 	print(f"Detected original ONT input is FASTA (no .fq file in processed_reads/)")
		# 	print(f"Using FASTA directly for hifiasm: {ont_extension_fasta}")
		# 	return ont_extension_fasta
		
		# 直接使用FASTA文件，不进行FA→FQ转换
		print(f"Using FASTA directly for hifiasm (FA→FQ conversion disabled): {ont_extension_fasta}")
		return ont_extension_fasta

	def combineExtensionReadsForReadsCommon(self):
		"""
		合并HiFi和ONT extension reads为单个文件用于readsCommon
		注意：hifiasm不需要合并，它通过--ul参数分别接收HiFi和ONT
		"""
		hifi_extension_fasta = self.extensionReads.extensionReads
		ont_extension_fasta = self.extensionReads.ont_extensionReads
		
		# 创建合并文件路径
		combined_file = self.extensionReads.roundInput.elongation.roundDir + "/combined_extension_reads.fa"
		
		print(f"[readsCommon] 合并HiFi和ONT extension reads: {hifi_extension_fasta} + {ont_extension_fasta} -> {combined_file}")
		
		try:
			with open(combined_file, 'w') as outfile:
				# 合并HiFi reads
				if os.path.exists(hifi_extension_fasta):
					print(f"添加HiFi reads: {hifi_extension_fasta}")
					with open(hifi_extension_fasta, 'r') as hifi_file:
						outfile.write(hifi_file.read())
				else:
					print(f"Warning: HiFi extension reads file not found: {hifi_extension_fasta}")
				
				# 合并ONT reads
				if os.path.exists(ont_extension_fasta):
					print(f"添加ONT reads: {ont_extension_fasta}")
					with open(ont_extension_fasta, 'r') as ont_file:
						outfile.write(ont_file.read())
				else:
					print(f"Warning: ONT extension reads file not found: {ont_extension_fasta}")
			
			print(f"合并完成，输出文件: {combined_file}")
			return combined_file
			
		except Exception as e:
			print(f"Error combining extension reads: {e}")
			return None

	def prepareONTHifiasmReads(self):
		"""
		为hifiasm准备ONT extension reads文件（用于Mixed模式的--ul参数）
		"""
		# 检查是否有ONT extension reads
		if not hasattr(self.extensionReads, 'ont_extensionReads'):
			print("No ONT extension reads available")
			return None

		if not os.path.exists(self.extensionReads.ont_extensionReads) or os.path.getsize(self.extensionReads.ont_extensionReads) == 0:
			print("ONT extension reads file not found or empty")
			return None

		# 禁用FA→FQ转换，直接使用FASTA文件
		ont_extension_fasta = self.extensionReads.ont_extensionReads
		# ont_extension_fastq = ont_extension_fasta.replace('.fa', '.fq')
		# 
		# # 简化逻辑：根据 processed_reads/ont_reads.fq 是否存在来决定
		# out_dir = self.extensionReads.roundInput.elongation.base.out
		# processed_ont_fq = os.path.join(out_dir, "processed_reads", "ont_reads.fq")
		# 
		# if os.path.exists(processed_ont_fq):
		# 	# 原始输入是FASTQ格式 → 转换extension reads为FASTQ
		# 	print(f"Detected original ONT input is FASTQ (found {processed_ont_fq})")
		# 	print(f"Converting ONT extension reads to FASTQ: {ont_extension_fasta} → {ont_extension_fastq}")
		# 	
		# 	ont_fastq_result = self._convert_extension_fasta_to_fastq(
		# 		ont_extension_fasta,
		# 		processed_ont_fq,
		# 		ont_extension_fastq
		# 	)
		# 
		# 	if ont_fastq_result:
		# 		print(f"✅ ONT extension FASTQ ready for --ul parameter: {ont_fastq_result}")
		# 		return ont_fastq_result
		# 	else:
		# 		print("⚠️ Failed to convert ONT extension reads to FASTQ")
		# 		return None
		# else:
		# 	# 原始输入是FASTA格式 → 返回FASTA
		# 	print(f"Detected original ONT input is FASTA (no .fq file in processed_reads/)")
		# 	print(f"Using FASTA for --ul parameter: {ont_extension_fasta}")
		# 	return ont_extension_fasta
		
		# 直接使用FASTA文件，不进行FA→FQ转换
		print(f"Using FASTA directly for --ul parameter (FA→FQ conversion disabled): {ont_extension_fasta}")
		return ont_extension_fasta

	def _convert_extension_fasta_to_fastq(self, extension_fasta, original_fastq, output_fastq):
		"""
		将筛选后的extension reads FASTA转换为FASTQ
		从原始FASTQ中提取对应reads的质量信息
		使用seqkit高性能工具优化
		"""
		import subprocess
		import tempfile
		import os
		
		if not os.path.exists(extension_fasta) or os.path.getsize(extension_fasta) == 0:
			print(f"Warning: Extension FASTA file not found or empty: {extension_fasta}")
			return None

		if not os.path.exists(original_fastq):
			print(f"Warning: Original FASTQ file not found: {original_fastq}")
			return None

		print(f"Converting {extension_fasta} to FASTQ format using seqkit (high performance)")
		print(f"Source: {extension_fasta}")
		print(f"Original: {original_fastq}")
		print(f"Output: {output_fastq}")

		try:
			# Step 1: 提取extension reads的ID列表
			extension_ids = []
			for record in SeqIO.parse(extension_fasta, "fasta"):
				extension_ids.append(record.id)
			
			print(f"Found {len(extension_ids)} extension reads to convert")
			
			if len(extension_ids) == 0:
				print("No extension reads found in FASTA file")
				return None

			# Step 2: 创建临时ID文件供seqkit使用
			with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_id_file:
				temp_id_path = temp_id_file.name
				for read_id in extension_ids:
					temp_id_file.write(f"{read_id}\n")
			
			print(f"Created temporary ID file: {temp_id_path}")

			# Step 3: 检测原始文件格式
			if original_fastq.endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
				format_type = "fastq"
				use_seqkit = True
			else:
				format_type = "fasta"
				use_seqkit = False
				print("Original file is FASTA format, will use Python fallback with dummy quality")

			# Step 4: 使用seqkit高效提取（仅当原始文件是FASTQ时）
			if use_seqkit:
				print("Using seqkit for high-performance extraction...")
				
				# 构造seqkit命令
				if original_fastq.endswith('.gz'):
					# 处理压缩文件
					seqkit_cmd = f"seqkit grep -f {temp_id_path} {original_fastq} -o {output_fastq}"
				else:
					# 处理未压缩文件
					seqkit_cmd = f"seqkit grep -f {temp_id_path} {original_fastq} -o {output_fastq}"
				
				print(f"Executing: {seqkit_cmd}")
				
				# 执行seqkit命令（无时间限制）
				start_time = time.time()
				result = subprocess.run(seqkit_cmd, shell=True, capture_output=True, text=True)
				end_time = time.time()
				
				if result.returncode == 0:
					print(f"seqkit extraction completed in {end_time - start_time:.2f} seconds")
					
					# 验证输出文件
					if os.path.exists(output_fastq) and os.path.getsize(output_fastq) > 0:
						# 统计转换的reads数量
						converted_count = 0
						try:
							for record in SeqIO.parse(output_fastq, "fastq"):
								converted_count += 1
						except:
							# 如果读取失败，使用简单的行数统计
							with open(output_fastq, 'r') as f:
								converted_count = sum(1 for line in f if line.startswith('@')) 
						
						print(f"Successfully converted {converted_count} reads to FASTQ format using seqkit")
						print(f"Performance improvement: ~{int(len(extension_ids) / max(end_time - start_time, 0.1))} reads/second")
						
						# 清理临时文件
						try:
							os.unlink(temp_id_path)
						except:
							pass
						
						return output_fastq if converted_count > 0 else None
					else:
						print("seqkit command succeeded but output file is empty or missing")
						use_seqkit = False  # 降级到Python实现
				else:
					print(f"seqkit command failed with return code {result.returncode}")
					print(f"stderr: {result.stderr}")
					print("Falling back to Python implementation...")
					use_seqkit = False  # 降级到Python实现

			# Step 5: Python fallback implementation (原有逻辑作为备用)
			if not use_seqkit:
				print("Using Python fallback implementation...")
				converted_count = 0
				
				with open(output_fastq, 'w') as out_f:
					for record in SeqIO.parse(original_fastq, format_type):
						if record.id in extension_ids:
							if format_type == "fastq":
								# Write as FASTQ with original quality
								SeqIO.write(record, out_f, "fastq")
							else:
								# If original was FASTA, generate dummy quality scores
								record.letter_annotations["phred_quality"] = [40] * len(record.seq)
								SeqIO.write(record, out_f, "fastq")
							converted_count += 1

				print(f"Python fallback completed: {converted_count} reads converted")
				
				# 清理临时文件
				try:
					os.unlink(temp_id_path)
				except:
					pass
				
				return output_fastq if converted_count > 0 else None

		except Exception as e:
			print(f"Error in seqkit conversion: {e}")
			# 清理临时文件
			try:
				if 'temp_id_path' in locals():
					os.unlink(temp_id_path)
			except:
				pass
			return None

	def combineMixedExtensionReads(self, output_file):
		"""
		合并HiFi和ONT extension reads用于readsCommon处理
		"""
		print("Combining HiFi and ONT extension reads for readsCommon processing...")

		with open(output_file, 'w') as out_f:
			# 添加HiFi extension reads
			if os.path.exists(self.extensionReads.extensionReads):
				print(f"Adding HiFi extension reads from: {self.extensionReads.extensionReads}")
				for record in SeqIO.parse(self.extensionReads.extensionReads, 'fasta'):
					# 添加前缀标识来源
					record.id = f"hifi_{record.id}"
					record.description = f"hifi_{record.description}"
					SeqIO.write(record, out_f, 'fasta')

			# 添加ONT extension reads
			if hasattr(self.extensionReads, 'ont_extensionReads') and os.path.exists(self.extensionReads.ont_extensionReads):
				print(f"Adding ONT extension reads from: {self.extensionReads.ont_extensionReads}")
				for record in SeqIO.parse(self.extensionReads.ont_extensionReads, 'fasta'):
					# 添加前缀标识来源
					record.id = f"ont_{record.id}"
					record.description = f"ont_{record.description}"
					SeqIO.write(record, out_f, 'fasta')
			else:
				print("No ONT extension reads found for combination")

		print(f"Combined extension reads saved to: {output_file}")
		return output_file

	def hifiasm(self):

		self.hifiasmDir=self.extensionReads.roundInput.elongation.roundDir+"/hifiasm"

		# Ensure hifiasm directory exists with proper error handling
		try:
			if not os.path.exists(self.hifiasmDir):
				os.makedirs(self.hifiasmDir, exist_ok=True)
				print(f"Created hifiasm directory: {self.hifiasmDir}")
			else:
				print(f"Using existing hifiasm directory: {self.hifiasmDir}")
		except Exception as e:
			print(f"Error creating hifiasm directory {self.hifiasmDir}: {e}")
			# Try to create parent directories if they don't exist
			try:
				parent_dir = os.path.dirname(self.hifiasmDir)
				if not os.path.exists(parent_dir):
					os.makedirs(parent_dir, exist_ok=True)
				os.makedirs(self.hifiasmDir, exist_ok=True)
				print(f"Successfully created hifiasm directory after creating parent directories")
			except Exception as e2:
				print(f"Failed to create hifiasm directory even after creating parents: {e2}")
				raise
		hifiasmID=self.hifiasmDir+"/PotentialExtensionContig.asm"
		self.hifiasmResult=hifiasmID+".p_ctg.fa"
		# Build hifiasm command based on data type
		threads = self.extensionReads.roundInput.elongation.base.thread

		# Convert extension reads FASTA to FASTQ for hifiasm
		reads_file = self.prepareHifiasmReads()

		# Check if reads preparation was successful
		if reads_file is None:
			print("Warning: Failed to prepare reads for hifiasm. Skipping hifiasm assembly.")
			# Set proper termination condition instead of creating empty files
			self.extensionSeqNote = "No extension reads available for hifiasm preparation"
			self.selectContigNote = "No extension contigs or reads found"
			self.hifiasmResultDict = {}
			return

		if self.data_type == 'mixed':
			# Mixed mode: HiFi + Ultra-long ONT
			# Prepare ONT extension reads FASTQ
			ont_extension_fastq = self.prepareONTHifiasmReads()

			if ont_extension_fastq and os.path.exists(ont_extension_fastq):
				self.hifiasmCommand = f"hifiasm -i -n 1 -o {hifiasmID} -t {threads} --ul {ont_extension_fastq} {reads_file}"
				print(f"Using Mixed mode for hifiasm assembly with filtered reads:")
				print(f"  HiFi extension reads: {reads_file}")
				print(f"  ONT extension reads: {ont_extension_fastq}")
			else:
				print("Warning: ONT extension reads not available, falling back to HiFi-only mode")
				self.hifiasmCommand = f"hifiasm -i -n 1 -o {hifiasmID} -t {threads} {reads_file}"
				print("Using HiFi-only mode for hifiasm assembly")
		elif self.data_type == 'ont':
			# ONT mode: use --ont parameter
			self.hifiasmCommand = f"hifiasm -i -n 1 -o {hifiasmID} -t {threads} --ont {reads_file}"
			print("Using ONT mode for hifiasm assembly")
		else:
			# HiFi mode: default mode for HiFi reads
			self.hifiasmCommand = f"hifiasm -i -n 1 -o {hifiasmID} -t {threads} {reads_file}"
			print("Using HiFi mode for hifiasm assembly")
		if os.path.exists(self.hifiasmResult)!=True or os.path.getsize(self.hifiasmResult)==0:
			print(f"Executing hifiasm command: {self.hifiasmCommand}")

			# Pre-execution checks
			print("=== Pre-execution diagnostics ===")
			print(f"Working directory: {os.getcwd()}")
			print(f"hifiasm directory: {self.hifiasmDir}")
			print(f"Expected result file: {self.hifiasmResult}")

			# Check input files
			command_parts = self.hifiasmCommand.split()
			input_files = [part for part in command_parts if part.endswith(('.fq', '.fastq', '.fq.gz', '.fastq.gz', '.fa', '.fasta'))]
			has_empty_files = False
			for input_file in input_files:
				if os.path.exists(input_file):
					file_size = os.path.getsize(input_file)
					print(f"Input file: {input_file} (size: {file_size} bytes)")
					if file_size == 0:
						print(f"❌ Error: Input file {input_file} is empty!")
						has_empty_files = True
				else:
					print(f"❌ Error: Input file {input_file} does not exist!")
					has_empty_files = True

			# Skip hifiasm execution if input files are problematic
			if has_empty_files:
				print("🚫 Skipping hifiasm execution due to empty or missing input files")
				print("This prevents hifiasm crashes and core file generation")
				return

			# Check if hifiasm is available and version compatibility
			import subprocess  # ensure available before first use
			try:
				hifiasm_check = subprocess.run("which hifiasm", shell=True, capture_output=True, text=True)
				if hifiasm_check.returncode == 0:
					hifiasm_path = hifiasm_check.stdout.strip()
					print(f"hifiasm found at: {hifiasm_path}")

					# Get hifiasm version and check compatibility
					version_check = subprocess.run("hifiasm --version", shell=True, capture_output=True, text=True)
					if version_check.returncode == 0:
						version_output = version_check.stdout.strip()
						print(f"hifiasm version: {version_output}")

						# Check for known problematic versions or provide recommendations
						if "0.16" in version_output or "0.17" in version_output:
							print("✅ Using recommended hifiasm version")
						elif "0.15" in version_output or "0.14" in version_output:
							print("⚠️  Using older hifiasm version - consider updating to 0.16+ for better stability")
						elif "0.18" in version_output or "0.19" in version_output:
							print("ℹ️  Using newer hifiasm version - if issues occur, consider downgrading to 0.16-0.17")
						else:
							print("ℹ️  Unknown hifiasm version - recommended versions: 0.16-0.17")
					else:
						print("hifiasm version: Unknown (version check failed)")
				else:
					print("❌ Error: hifiasm not found in PATH")
					print("Please ensure hifiasm is installed and accessible")
					return
			except Exception as e:
				print(f"Error checking hifiasm availability: {e}")
				print("Proceeding with caution...")

			# Capture pre-execution system snapshot
			try:
				pre_snap = os.path.join(self.hifiasmDir, "hifiasm.pre.snapshot.txt")
				with open(pre_snap, 'w') as sf:
					for cmd in [
						"date",
						"uname -a || true",
						"nproc || true",
						"uptime || true",
						"free -m || true",
						"df -h . || true",
						"top -b -n1 | head -n 30 || true"
					]:
						try:
							res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
							sf.write(f"\n===== {cmd} =====\n")
							sf.write(res.stdout or res.stderr or "")
						except Exception as _:
							pass
			except Exception as _:
				pass
			print("=== Executing hifiasm ===")
			try:
				# Use subprocess with additional safety measures
				import subprocess
				import signal
				import resource
				import time

				# Set CPU time limit to prevent runaway processes (memory managed by LSF)
				def set_limits():
					try:
						# Only limit CPU time to 2 hours (let LSF manage memory)
						resource.setrlimit(resource.RLIMIT_CPU, (7200, 7200))
						print("✅ CPU time limit set: 2 hours (memory managed by LSF)")
					except Exception as e:
						print(f"⚠️  Could not set CPU time limit: {e}")

				print(f"🚀 Starting hifiasm with 1-hour timeout...")
				start_time = time.time()

				# Execute with timeout and resource limits (reduced to 1 hour)
				result = subprocess.run(
					self.hifiasmCommand,
					shell=True,
					capture_output=True,
					text=True,
					timeout=3600,  # 1 hour timeout (reduced from 2 hours)
					preexec_fn=set_limits
				)
				# Persist stdout/stderr
				try:
					with open(os.path.join(self.hifiasmDir, 'hifiasm.stdout.log'), 'w') as so:
						so.write(result.stdout or '')
					with open(os.path.join(self.hifiasmDir, 'hifiasm.stderr.log'), 'w') as se:
						se.write(result.stderr or '')
				except Exception:
					pass

				end_time = time.time()
				execution_time = end_time - start_time
				print(f"⏱️  hifiasm execution time: {execution_time:.1f} seconds")

				print(f"hifiasm return code: {result.returncode}")

				# Check for core files after hifiasm execution (detection only, no cleanup)
				core_files_detected = []
				try:
					current_dir_files = os.listdir('.')
					core_files_detected = [f for f in current_dir_files if f.startswith('core.')]
					if core_files_detected:
						print(f"🚨 CORE FILES DETECTED: {core_files_detected}")
						print("⚠️  Core files indicate hifiasm crashed - NOT automatically cleaning up")
						print("📋 Please investigate the cause before manually removing core files")
				except Exception as e:
					print(f"Error checking for core files: {e}")

				if result.returncode != 0:
					print(f"Warning: hifiasm command failed with return code {result.returncode}")
					print(f"Error output: {result.stderr}")
					print(f"Standard output: {result.stdout}")

					if core_files_detected:
						print("🚨 HIFIASM CRASHED (core files detected)")
						print("Possible causes and solutions:")
						print("1. Memory access violation → Try reducing input size or updating hifiasm")
						print("2. Incompatible hifiasm version → Check version compatibility")
						print("3. Corrupted input data → Validate input file integrity")
						print("4. System resource limits → Increase memory/swap space")
						print("5. Consider using alternative assembly methods")

					print("Will continue with fallback readCommon method")
				else:
					print("✅ hifiasm command completed successfully")
					if core_files_detected:
						print("⚠️  Note: Core files were detected but hifiasm reported success")
					# Capture post-execution snapshot on success
					try:
						post_snap = os.path.join(self.hifiasmDir, "hifiasm.post.snapshot.txt")
						with open(post_snap, 'w') as sf:
							for cmd in [
								"date",
								"uptime || true",
								"free -m || true",
								"df -h . || true",
								"top -b -n1 | head -n 30 || true"
							]:
								try:
									res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
									sf.write(f"\n===== {cmd} =====\n")
									sf.write(res.stdout or res.stderr or "")
								except Exception:
									pass
					except Exception:
						pass

			except subprocess.TimeoutExpired as te:
				print("⏰ TIMEOUT: hifiasm command timed out after 1 hour")
				print("🔧 Possible solutions:")
				print("   1. Reduce input data size")
				print("   2. Increase LSF memory allocation (-M parameter)")
				print("   3. Use alternative assembly methods")
				print("   4. Consider increasing timeout for large datasets")
				# Persist any partial stdout/stderr if available
				try:
					with open(os.path.join(self.hifiasmDir, 'hifiasm.stdout.log'), 'w') as so:
						so.write(getattr(te, 'output', '') or '')
					with open(os.path.join(self.hifiasmDir, 'hifiasm.stderr.log'), 'w') as se:
						se.write(getattr(te, 'stderr', '') or '')
				except Exception:
					pass

				# Check for core files after timeout (detection only)
				try:
					core_files = [f for f in os.listdir('.') if f.startswith('core.')]
					if core_files:
						print(f"🚨 Core files detected after timeout: {core_files}")
						print("⚠️  This indicates hifiasm crashed during timeout")
				except:
					pass
				# Capture post-execution snapshot even on timeout
				try:
					post_snap = os.path.join(self.hifiasmDir, "hifiasm.post.snapshot.txt")
					with open(post_snap, 'w') as sf:
						for cmd in [
							"date",
							"uptime || true",
							"free -m || true",
							"df -h . || true",
							"top -b -n1 | head -n 30 || true"
						]:
							try:
								res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
								sf.write(f"\n===== {cmd} =====\n")
								sf.write(res.stdout or res.stderr or "")
							except Exception:
								pass
				except Exception:
					pass

			except Exception as e:
				print(f"❌ Exception while executing hifiasm: {e}")
				print("🔧 Will continue with readCommon fallback method")
				print("Will continue with fallback assembly methods")

			# Verify hifiasm directory still exists after command execution
			if not os.path.exists(self.hifiasmDir):
				print(f"Warning: hifiasm directory was removed during command execution, recreating: {self.hifiasmDir}")
				try:
					os.makedirs(self.hifiasmDir, exist_ok=True)
				except Exception as e:
					print(f"Error recreating hifiasm directory: {e}")
		
		# Initialize hifiasmResultInput variable to prevent errors when file not found
		self.hifiasmResultInput = None

		# Check if hifiasm directory exists before listing files
		try:
			if os.path.exists(self.hifiasmDir) and os.path.isdir(self.hifiasmDir):
				for files in os.listdir(self.hifiasmDir):
					if '.p_ctg.gfa' in files:
						if 'bp.p_ctg.gfa' in files:
							self.hifiasmResultInput=self.hifiasmDir+"/"+files
						else:
							if 'hap' not in files:
								self.hifiasmResultInput=self.hifiasmDir+"/"+files
			else:
				print(f"Warning: hifiasm directory does not exist or is not a directory: {self.hifiasmDir}")
		except Exception as e:
			print(f"Error listing files in hifiasm directory {self.hifiasmDir}: {e}")
			print("This may indicate hifiasm failed to run or the directory was corrupted")
		
		# If no valid file found, use default filename
		if self.hifiasmResultInput is None:
			self.hifiasmResultInput = hifiasmID + ".p_ctg.gfa"
			print(f"Warning: No valid p_ctg.gfa file found, using default filename: {self.hifiasmResultInput}")

		# Check if hifiasm result file exists before trying to open it
		if not os.path.exists(self.hifiasmResultInput):
			print(f"Error: hifiasm result file does not exist: {self.hifiasmResultInput}")
			print("This indicates hifiasm failed to produce output. Will create empty result file.")

			# Create empty result file to prevent downstream errors
			try:
				with open(self.hifiasmResult, 'w') as empty_file:
					pass  # Create empty file
				print(f"Created empty hifiasm result file: {self.hifiasmResult}")
			except Exception as e:
				print(f"Error creating empty result file: {e}")

			# Set empty result dictionary
			self.hifiasmResultDict = {}
			return

		try:
			file1=open(self.hifiasmResultInput,'r')
			file2=open(self.hifiasmResult,'w')
			hifiasmResultDict={}

			for rseq in file1:
				rseq1=rseq.rstrip().split('\t')
				if rseq1[0]=='S':
					l='>'+rseq1[1]+"\t"+'\t'.join(rseq1[3:])+"\n"+rseq1[2]+"\n"
					file2.writelines(l)
				else:
					if rseq1[1] in hifiasmResultDict:
						listhifi=hifiasmResultDict[rseq1[1]]
					else:
						listhifi=[]
					listhifi.append(rseq1[4])
					hifiasmResultDict[rseq1[1]]=listhifi

			file1.close()
			file2.close()
			self.hifiasmResultDict=hifiasmResultDict
			print(f"Successfully processed hifiasm result file with {len(hifiasmResultDict)} contigs")

		except Exception as e:
			print(f"Error processing hifiasm result file: {e}")
			print("This may indicate corrupted hifiasm output or file access issues")

			# Ensure files are closed if they were opened
			try:
				if 'file1' in locals():
					file1.close()
				if 'file2' in locals():
					file2.close()
			except:
				pass

			# Set empty result dictionary
			self.hifiasmResultDict = {}

			# Create empty result file if it doesn't exist
			if not os.path.exists(self.hifiasmResult):
				try:
					with open(self.hifiasmResult, 'w') as empty_file:
						pass
				except Exception as e2:
					print(f"Error creating empty result file: {e2}")

	def readlog(self):
		logfilet=open(self.log,'r')
		self.selectContigNote=''
		for row in logfilet:
			row1=row.rstrip().split('\t')
			if row1[0]=='hifiasmDir':
				self.hifiasmDir=row1[1]
			elif row1[0]=='hifiasmCommand':
				self.hifiasmCommand=row1[1]
			elif row1[0]=='hifiasmResult':
				self.hifiasmResult=row1[1]
			elif row1[0]=='hifiasmResultDict':
				if len(row1)>1:
					row2=row1[1].split(':')
					hifiasmResultDict={}
					for i in row2:
						row3=i.split(';')
						hifiasmResultDict[row3[0]]=row3[1:]
					self.hifiasmResultDict=hifiasmResultDict
				else:	
					self.hifiasmResultDict={}

			elif row1[0]=='readCommonResult':
				self.readCommonResult=row1[1]
			elif row1[0]=='extensionSeqNote':
				self.extensionSeqNote=row1[1]
			elif row1[0]=='extensionContigs':
				self.extensionContigs=row1[1]

			elif row1[0]=='potentialExtensionContigsAln':
				self.potentialExtensionContigsAln=row1[1]
			elif row1[0]=='selectContigIdentity':
				self.selectContigIdentity=float(row1[1])
			elif row1[0]=='selectContigDistance':
				self.selectContigDistance=float(row1[1])
			elif row1[0]=='selectContigAlnLength':
				self.selectContigAlnLength=float(row1[1])
			elif row1[0]=='contigAlnMerge':
				self.contigAlnMerge=bool(row1[1])
			elif row1[0]=='contigAlnMergeIdentity':
				self.contigAlnMergeIdentity=float(row1[1])

			elif row1[0]=='potentialExtensionContigsAlnDict':
				self.potentialExtensionContigsAlnDict={}
				for i in row1[1:]:
					i1=i.split('-')
					if "ovl" in i1:
						k1,k2,k3,a,b,c,d,len1=i1
						k=k1+"-"+k2+"-"+k3
					else:
						k,a,b,c,d,len1=i1
					alist=[]
					a1=a.rstrip().split(';')
					for a2 in a1:
						if a2!='':
							a3=a2.split(',')
							alist.append([int(a3[0]),int(a3[1])])
					blist=[]
					b1=b.rstrip().split(';')
					for b2 in b1:
						if b2!='':
							b3=b2.split(',')
							blist.append([int(b3[0]),int(b3[1])])
					clist=[]
					c1=c.rstrip().split(';')
					for c2 in c1:
						if c2!='':
							c3=c2.split(',')
							clist.append([int(c3[0]),int(c3[1])])
					dlist=[]
					d1=d.rstrip().split(';')
					for d2 in d1:
						if d2!='':
							d3=d2.split(',')
							dlist.append([int(d3[0]),int(d3[1])])
					self.potentialExtensionContigsAlnDict[k]=[alist,blist,clist,dlist,int(len1)]
			elif row1[0]=='selectExtensionContigsAln':
				self.selectExtensionContigsAln=[]
				line1='\t'.join(row1[1:])
				line2=line1.split(';')
				for i in line2:
					if i!='':
						i1=i.split('\t')
						b=i1[-1].split('-')[-1]
						a='\t'.join(i1[:-1])+"\t"+i1[-1].split('-')[0]
						self.selectExtensionContigsAln.append([a+"\n",int(b)])
			elif row1[0]=='maxextensionLen':
				self.maxextensionLen=int(row1[1])
			elif row1[0]=='selectContigNote':
				self.selectContigNote=self.selectContigNote+'\t'.join(row1[1:])+"\n"
			elif row1[0]=='FuzzyAln':
				self.FuzzyAln=[]
				if len(row1)>1:
					line1=row1[1].rstrip().split(';')
					for i in line1:
						i1=i.split('-')
						self.FuzzyAln.append(i1)
			elif row1[0]=='extensionContigID':
				self.extensionContigID=row1[1].split(';')
			elif row1[0]=='extensionLength':
				self.extensionLength=int(row1[1])
			elif row1[0]=='extensionSequence':
				self.extensionSequence=row1[1]
		logfilet.close()

	def cleanup_memory(self):
		"""Clean up memory by clearing large data structures"""
		import gc
		
		# Clear dictionaries
		for attr in ['hifiasmResultDict', 'potentialExtensionContigsAlnDict', 'contigDict', 'readsDict']:
			if hasattr(self, attr):
				setattr(self, attr, {})
		
		# Clear lists
		for attr in ['selectExtensionContigsAln', 'extensionContigID', 'contigAlnList', 'FuzzyAln']:
			if hasattr(self, attr):
				setattr(self, attr, [])
		
		# Clear sequence data
		if hasattr(self, 'extensionSequence'):
			self.extensionSequence = None
		if hasattr(self, 'extensionContigs'):
			self.extensionContigs = None
		
		# Clear ExtensionReads reference
		if hasattr(self, 'extensionReads'):
			self.extensionReads = None
		
		gc.collect()
