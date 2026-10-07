"""A small labelled corpus for checking RETRIEVAL_RELEVANCE_THRESHOLD.

NOTES are three plausible study documents (the kind a student uploads for a data
structures / databases course). ON_TOPIC questions are answerable from them, in
a mix of phrasings: full questions, keywords, and paraphrases that avoid the
notes' own wording. OFF_TOPIC questions are what the tutor must refuse: some
are plainly unrelated, and some are the harder case, a real computer-science
question the notes do not cover.

The threshold depends on the embedding model and on chunk size, so this corpus
is run against the real embedder (tests/test_relevance_threshold.py). Nothing
here is made up to fit a number: the lists were written first and the
threshold was chosen from the distributions they produce.
"""

NOTES = {
    "Hash tables": """
A hash table stores key-value pairs so that a value can be found from its key in constant time on average. The table is an array of buckets. To insert a key, a hash function turns the key into an integer, and that integer taken modulo the number of buckets gives the bucket where the entry belongs. Looking a key up repeats the same computation and then checks that bucket.

A good hash function spreads keys evenly across the buckets and is cheap to compute. If many keys land in the same bucket the table slows down, because the entries in that bucket have to be searched one by one. Two different keys that map to the same bucket are said to collide, and every practical hash table needs a way to handle collisions.

Separate chaining handles a collision by keeping a linked list in each bucket. A new entry is appended to the list of its bucket, and a lookup walks that list comparing keys. The cost of an operation is proportional to the length of the list, which is why the average list length matters so much.

Open addressing stores every entry in the array itself. When the preferred slot is taken, the table probes other slots in a fixed sequence until it finds a free one. Linear probing tries the next slot, then the one after, and so on. It is simple and cache friendly but suffers from clustering, where runs of occupied slots grow longer and make later probes slower. Quadratic probing and double hashing reduce clustering.

The load factor is the number of stored entries divided by the number of buckets. As the load factor rises, collisions become more frequent. Most implementations resize when the load factor passes a threshold, commonly 0.75 for chaining: they allocate a larger array, usually twice the size, and rehash every key into it. Resizing is expensive but happens rarely enough that insertion stays constant time when averaged over many operations, which is called amortized constant time.

Deleting from an open-addressed table needs care. Simply emptying a slot would break the probe sequence of other keys, so the slot is marked with a tombstone that lookups skip over but insertions may reuse.
""",
    "Database normalization": """
Normalization is the process of organizing the tables of a relational database to reduce redundancy and prevent update anomalies. A table that stores the same fact in many rows invites inconsistency: if one copy is changed and another is not, the database contradicts itself. The three classic anomalies are the insertion anomaly, where a fact cannot be recorded without unrelated data, the update anomaly, where one fact must be changed in many places, and the deletion anomaly, where deleting a row destroys an unrelated fact.

A table is in first normal form when every column holds a single atomic value and there are no repeating groups. A column that contains a comma separated list of phone numbers violates first normal form, and the fix is to move the phone numbers into their own table with one row per number.

Second normal form applies to tables whose primary key is made of several columns. The table must be in first normal form and every non-key column must depend on the whole key, not on just part of it. If the key is the pair of student and course, a column holding the student's name depends only on the student, which is a partial dependency, and the name should move to a student table.

Third normal form removes transitive dependencies. A non-key column must depend directly on the key and not on another non-key column. If an employee table stores the department number and the department name, the name depends on the department number rather than on the employee, so the department details belong in a separate department table that the employee row references by key.

Boyce-Codd normal form is a stricter version of third normal form. It requires that for every functional dependency, the determining set of columns is a superkey. A functional dependency X determines Y means that two rows with the same value of X always have the same value of Y. Normalizing too far can force many joins, so designers sometimes denormalize on purpose to speed up reads.
""",
    "Sorting algorithms": """
Sorting arranges the elements of a list in order. Bubble sort repeatedly steps through the list, compares adjacent elements and swaps them if they are in the wrong order, so the largest unsorted element bubbles to the end on each pass. It takes quadratic time in the worst case and is rarely used except for teaching. Insertion sort builds the sorted list one element at a time by inserting each new element into its correct place among the ones already sorted. It runs in linear time on data that is already nearly sorted, which makes it a good choice for small arrays.

Merge sort is a divide and conquer algorithm. It splits the list into two halves, sorts each half recursively and then merges the two sorted halves into one by repeatedly taking the smaller front element. Its running time is n log n in every case, but the merge step needs extra memory proportional to the size of the list. Merge sort is stable, meaning that equal elements keep their original relative order.

Quicksort picks a pivot element and partitions the list into elements smaller than the pivot and elements larger than it, then sorts each part recursively. On average it runs in n log n time and sorts in place, which is why it is fast in practice. Its worst case is quadratic and happens when the pivot is repeatedly the smallest or largest element, for example when always choosing the first element of an already sorted list. Choosing a random pivot or the median of three makes the worst case unlikely.

Heap sort builds a binary max heap from the data and then repeatedly removes the largest element to the end of the array. It guarantees n log n time and needs no extra memory, but it is not stable. Counting sort and radix sort are not comparison sorts: they use the values of the keys directly and can run in linear time when the range of keys is small.
""",
}

# Answerable from NOTES.
ON_TOPIC = [
    "What is a hash function?",
    "How does separate chaining resolve collisions?",
    "What is the load factor of a hash table?",
    "Why does a hash table resize and rehash its keys?",
    "What is linear probing and what problem does it have?",
    "What is a tombstone in open addressing?",
    "Explain clustering",
    "load factor 0.75",
    "How are two keys that map to the same bucket handled?",
    "What does it mean for an operation to be amortized constant time?",
    "What are the insertion, update and deletion anomalies?",
    "What is first normal form?",
    "Explain second normal form and partial dependency",
    "Why does third normal form remove transitive dependencies?",
    "What is a functional dependency?",
    "How is Boyce-Codd normal form different from third normal form?",
    "Why would someone denormalize a database?",
    "A column stores a comma separated list of phone numbers, which rule does that break?",
    "How does merge sort work?",
    "What is the worst case of quicksort and when does it happen?",
    "Which sorting algorithms are stable?",
    "Why is insertion sort good for nearly sorted data?",
    "What is a pivot in quicksort?",
    "How does heap sort work and does it need extra memory?",
    "difference between comparison sorts and counting sort",
    # Paraphrases that avoid the notes' own words.
    "How do you stop the lookup structure from getting slow when it fills up?",
    "Why is it bad to store the same fact in many rows?",
    "Which algorithm splits the list in half and combines the sorted halves?",
]

# Must be refused. The first group is plainly unrelated; the second is the hard
# case, genuine computer-science questions that the notes do not cover.
OFF_TOPIC_UNRELATED = [
    "What ingredients go into a chocolate cake?",
    "Who won the football world cup in 2010?",
    "What is the capital of France?",
    "How do I get a refund for my flight?",
    "hello",
    "What is the boiling point of water at altitude?",
    "Tell me a joke about cats",
    "How many calories are in a banana?",
]
OFF_TOPIC_ADJACENT = [
    "What is a B-tree and how does it index a disk?",
    "Explain TCP congestion control",
    "How does gradient descent minimize a loss function?",
    "What is the difference between a process and a thread?",
    "How does public key encryption work?",
    "Explain Dijkstra's shortest path algorithm",
    "What is a deadlock in an operating system?",
    "How do I set up database replication across data centers?",
]
OFF_TOPIC = OFF_TOPIC_UNRELATED + OFF_TOPIC_ADJACENT
