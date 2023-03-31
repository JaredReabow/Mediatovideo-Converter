find . -type f -name '*media' >> list1.txt
sort list1.txt >> list2.txt
while read line; do ffprobe $line; if [ $? = "1" ]; then echo $line; fi; done < list2.txt >> errors.txt
awk 'NR==FNR{a[$0];next} !($0 in a)' errors.txt list2.txt > temp; mv temp list2.txt
while read line; do echo "file '$line'"; done < list2.txt >> list3.txt
ffmpeg -f concat -safe 0 -i list3.txt -c copy output.mkv
rm list1.txt list2.txt list3.txt errors.txt