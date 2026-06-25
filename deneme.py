def maxarraysayisi(array:list[int]):
    max_val = array[0]
    for i in range(len(array)):
        if array[i] > max_val:
            max_val = array[i]
    return max_val 
        
