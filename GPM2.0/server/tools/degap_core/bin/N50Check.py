import re
import sys
import operator
import Bio
from Bio import SeqIO

def N50Check(parameters):
	# 支持4-5个参数：genomeSeq, seedLen, ctgSeq, logfile, [trim_edges=False]
	trim_edges = False  # 默认不裁剪边缘，保留完整序列
	if len(parameters) >= 4:
		genomeSeq,seedLen,ctgSeq,logfile = parameters[:4]
		if len(parameters) >= 5:
			trim_edges = parameters[4]  # 第5个参数控制是否裁剪边缘
		file1=open(logfile,'w')
		file2=open(ctgSeq,'w')
	else:
		genomeSeq,logfile=parameters
		file1=open(logfile,'w')
	i=0
	d1={}
	i1=0
	i4=0
	d2={}
	d3={}
	for gseq in SeqIO.parse(genomeSeq,"fasta"):
		i2=0
		i3=0
		
		Seq1=str(gseq.seq).upper()
		seq1=''
		seq2=Seq1.split("N")
		seq3=[x for x in seq2 if x!= '']
		if len(seq3)>1:
			i4+=1
		for j in seq3:
			if len(parameters)==4:
				if len(j)>seedLen:
					i1+=len(j)
					i3+=len(j)
					d1[i]=len(j)
					d2[i]=j
					d3[i]=gseq.id
					i2+=1
					i=i+1
			else:
				i1+=len(j)
				i3+=len(j)
				d1[i]=len(j)
				d2[i]=j
				d3[i]=gseq.id
				i2+=1
				i=i+1
		l1=sorted(d2.items(), key=operator.itemgetter(1), reverse=True)
	if len(l1)==0:
		for gseq in SeqIO.parse(genomeSeq,"fasta"):
			Seq1=str(gseq.seq).upper()
			seq1=''
			seq2=Seq1.split("N")
			seq3=[x for x in seq2 if x!= '']
			if len(seq3)>1:
				i4+=1
			for j in seq3:
				i1+=len(j)
				i3+=len(j)
				d1[i]=len(j)
				d2[i]=j
				d3[i]=gseq.id
				i2+=1
				i=i+1
		l1=sorted(d2.items(), key=operator.itemgetter(1), reverse=True)
					
	l2=sorted(d1.items(), key=operator.itemgetter(1), reverse=True)
	logline="total Non-N base:\t"+str(i1)+"\n"
	logline=logline+"total contig number:\t"+str(len(d1))+"\n"
	H=i1/2.0
	j1=0
	# Fix: check if l2 is not empty before accessing
	if l2:
		logline=logline+"max contig length:\t"+str(l2[0][1])+"\n"
		logline=logline+"min contig length:\t"+str(l2[-1][1])+"\n"
	else:
		logline=logline+"max contig length:\t0\n"
		logline=logline+"min contig length:\t0\n"
	for j in l2:
		j1+=int(j[1])
		if j1>H:
			logline=logline+"N50:\t"+str(j[1])+"\n"
			break
	if len(parameters)>=4:
		for k,v in d2.items():
			if trim_edges:
				# 裁剪两端各 seedLen/2
				seedLen1=int(seedLen/2)
				seq_out = v[seedLen1:-seedLen1]
			else:
				# 不裁剪，保留完整序列
				seq_out = v
			row='>Contig-'+str(k)+"\t"+d3[k]+"\n"+seq_out+"\n"
			file2.writelines(row)
		file2.close()
	print (logline)
	file1.writelines(logline)
	file1.close()
	
