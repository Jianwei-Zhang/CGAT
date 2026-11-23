// Read-only control, not a mapper. C++17. Input: Q<tab>sequence or T<tab>sequence.
// For 100+ paired bases at >=95% column identity, at least one partition chunk
// of 100..199 columns has >=95% identity. Among n columns with e errors it has
// >= n-k*e-(k-1) aligned identical k-mers: at least 5 for k=16, 53 for k=8.
// Its starts lie within two adjacent 200-base bins on each axis in one strand.
// Repeats, ambiguity and budget limits can only retain extra pairs.
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {
constexpr unsigned B = 200;
unsigned code(char c) {
    switch(c) { case 'A':return 0; case 'C':return 1; case 'G':return 2; case 'T':return 3; default:return 4; }
}
bool clean(const std::string& s) { return std::all_of(s.begin(),s.end(),[](char c){return code(c)<4;}); }
std::string reverse_complement(const std::string& s) {
    std::string r; r.reserve(s.size());
    for(auto it=s.rbegin(); it!=s.rend(); ++it) r.push_back("TGCA"[code(*it)]);
    return r;
}
template<unsigned K, class F>
bool scan(const std::string& s, unsigned lo, unsigned end_starts, F visit) {
    if (s.size()<K) return false;
    const unsigned stop=std::min<unsigned>(end_starts,s.size()-K+1);
    if(lo>=stop) return false;
    const uint32_t mask=uint32_t((uint64_t(1)<<(2*K))-1);
    uint32_t key=0;
    for(unsigned j=lo; j<lo+K-1; ++j) key=(key<<2)|code(s[j]);
    for(unsigned i=lo;i<stop;++i){
        key=((key<<2)|code(s[i+K-1]))&mask;
        if(visit(i,key)) return true;
    }
    return false;
}
template<unsigned K>
bool shared(const std::string& q, unsigned qb, const std::string& t, unsigned tb, unsigned wanted) {
    std::unordered_map<uint32_t,unsigned> count;
    scan<K>(q,qb*B,(qb+2)*B,[&](unsigned,uint32_t k){++count[k];return false;});
    return scan<K>(t,tb*B,(tb+2)*B,[&](unsigned,uint32_t k){auto it=count.find(k);
        if(it!=count.end() && it->second){--it->second;return --wanted==0;} return false;});
}
struct Strand {
    std::string seq;
    std::unordered_map<uint32_t,std::vector<unsigned>> bins;
    explicit Strand(std::string s):seq(std::move(s)) {
        scan<16>(seq,0,seq.size(),[&](unsigned pos,uint32_t k){auto &v=bins[k]; unsigned b=pos/B;
            if(v.empty()||v.back()!=b) v.push_back(b);
            return false;});
    }
    bool possible(const std::string &t) const {
        std::unordered_set<uint64_t> seen;
        unsigned visits=0;
        return scan<16>(t,0,t.size(),[&](unsigned tp,uint32_t k){auto it=bins.find(k); if(it==bins.end())return false;
            unsigned b=tp/B;
            for(unsigned a:it->second){
                if(++visits>200000) return true; // abstain on prolific repeats
                for(unsigned qa=(a?a-1:0);qa<=a;++qa) for(unsigned tb=(b?b-1:0);tb<=b;++tb){
                    if(!seen.insert((uint64_t(qa)<<32)|tb).second)continue;
                    if(seen.size()>8192 || (shared<16>(seq,qa,t,tb,5) && shared<8>(seq,qa,t,tb,53)))return true;
                }
            }
            return false;});
    }
};
}
int main(){
    std::ios::sync_with_stdio(false); std::cin.tie(nullptr);
    bool have=false,valid=false; size_t length=0; std::unique_ptr<Strand> fwd,rev;
    std::string line;
    while(std::getline(std::cin,line)){
        if(line.size()<3 || line[1]!='\t' || line.size()>10000002) return 2;
        std::string s=line.substr(2);
        if(line[0]=='Q'){
            have=true;length=s.size();valid=clean(s);fwd.reset();rev.reset();
            if(valid && length>=100){ fwd=std::make_unique<Strand>(s);rev=std::make_unique<Strand>(reverse_complement(s)); }
        } else if(line[0]=='T' && have){
            if(std::min(length,s.size())<100) std::cout<<"short\n";
            else if(!valid || !clean(s)) std::cout<<"uncertain\n";
            else std::cout<<((fwd->possible(s)||rev->possible(s))?"possible\n":"excluded\n");
        } else return 2;
    }
    return std::cin.eof() && have ? 0 : 2;
}
