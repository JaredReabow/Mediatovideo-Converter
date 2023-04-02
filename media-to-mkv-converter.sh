find . -type f -name '*media' >> unsortedlist.txt
sort unsortedlist.txt >> sortedlist.txt
while read line; do ffprobe $line; if [ $? = "1" ]; then echo $line; fi; done < sortedlist.txt >> corruptfiles.txt
awk 'NR==FNR{a[$0];next} !($0 in a)' corruptfiles.txt sortedlist.txt > temp; mv temp sortedlist.txt
while read line; do echo "file '$line'"; done < sortedlist.txt >> sortedlistwithoutcorruptfiles.txt
ffmpeg -f concat -safe 0 -i sortedlistwithoutcorruptfiles.txt -c copy outputvideo.mkv
rm unsortedlist.txt sortedlist.txt sortedlistwithoutcorruptfiles.txt corruptfiles.txt